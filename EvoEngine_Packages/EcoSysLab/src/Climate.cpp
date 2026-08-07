#include "Climate.hpp"
#include "EcoSysLabSerializationAdapters.hpp"

#include "AssetManager.hpp"
#include "DsColliders.hpp"
#include "EcoSysLabLayer.hpp"
#include "EditorLayer.hpp"
#include "Tree.hpp"

using namespace eco_sys_lab_package;

bool ClimateDescriptor::DrawGui(const std::shared_ptr<EditorLayer>& editor_layer) {
  bool changed = false;
  if (ImGui::Button("Instantiate")) {
    const auto scene = ApplicationContext::Get().GetActiveScene();
    const auto climate_entity = scene->CreateEntity(GetTitle());
    const auto climate = scene->GetOrSetPrivateComponent<Climate>(climate_entity).lock();
    climate->climate_descriptor_ref = GetSelf();
  }
  return changed;
}

std::shared_ptr<Texture2D> ClimateDescriptor::GenerateThumbnailTexture() {
  static std::shared_ptr<Texture2D> thumbnail;
  if (!thumbnail) {
    thumbnail = AssetManager::CreateTemporaryAsset<Texture2D>();
    thumbnail->Import(
        std::filesystem::absolute(std::filesystem::path("./EcoSysLabResources") / "Icons/ClimateDescriptor.png"));
  }
  return thumbnail;
}

void eco_sys_lab_package::SerializeClimateDescriptor(YAML::Emitter& out, const ClimateDescriptor& target) {
}

void eco_sys_lab_package::DeserializeClimateDescriptor(const YAML::Node& in, ClimateDescriptor& target) {
}

bool Climate::DrawGui(const std::shared_ptr<EditorLayer>& editor_layer) {
  bool changed = false;
  if (editor_layer->DragAndDropButton<ClimateDescriptor>(climate_descriptor_ref, "ClimateDescriptor", true)) {
    InitializeClimateModel();
    changed = true;
  }

  if (climate_descriptor_ref.Get<ClimateDescriptor>()) {
  }
  return changed;
}

void eco_sys_lab_package::SerializeClimate(YAML::Emitter& out, const Climate& target) {
  target.climate_descriptor_ref.Save("climate_descriptor_ref", out);
}

void Climate::CollectAssetRef(std::vector<AssetRef>& list) {
  list.push_back(climate_descriptor_ref);
}

void Climate::InitializeClimateModel() {
  if (const auto climate_descriptor = climate_descriptor_ref.Get<ClimateDescriptor>()) {
    const auto params = climate_descriptor->climate_parameters;
    climate_model.Initialize(params);
  }
}

void Climate::PrepareForGrowth() {
  const auto eco_sys_lab_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  const auto scene = GetScene();
  const std::vector<Entity>* tree_entities = scene->UnsafeGetPrivateComponentOwnersList<Tree>();
  if (!tree_entities || tree_entities->empty())
    return;

  auto& estimator = climate_model.environment_grid;
  auto min_bound = estimator.voxel_grid.GetMinBound();
  auto max_bound = estimator.voxel_grid.GetMaxBound();
  bool bound_changed = false;
  struct GrowthObstacle {
    glm::vec3 min_bound;
    glm::vec3 max_bound;
    float shadow;
    float biomass;
    unsigned entity_index;
  };
  std::vector<GrowthObstacle> growth_obstacles;
  if (const auto* obstacle_entities = scene->UnsafeGetPrivateComponentOwnersList<DsBoxCollider>()) {
    for (const auto& obstacle_entity : *obstacle_entities) {
      const auto obstacle = scene->GetOrSetPrivateComponent<DsBoxCollider>(obstacle_entity).lock();
      if (!obstacle || !obstacle->IsEnabled() || !scene->IsEntityEnabled(obstacle_entity) ||
          !obstacle->affect_tree_growth)
        continue;
      const auto transform = scene->GetDataComponent<GlobalTransform>(obstacle_entity);
      const auto rotation = glm::mat3_cast(transform.GetRotation());
      const auto absolute_rotation =
          glm::mat3(glm::abs(rotation[0]), glm::abs(rotation[1]), glm::abs(rotation[2]));
      const auto half_extent = absolute_rotation * glm::abs(obstacle->scale * transform.GetScale());
      const auto obstacle_min = transform.GetPosition() - half_extent;
      const auto obstacle_max = transform.GetPosition() + half_extent;
      growth_obstacles.push_back({obstacle_min, obstacle_max, obstacle->tree_growth_shadow,
                                  obstacle->tree_growth_biomass, obstacle_entity.GetIndex()});
      if (obstacle_min.x <= min_bound.x || obstacle_min.y <= min_bound.y || obstacle_min.z <= min_bound.z ||
          obstacle_max.x >= max_bound.x || obstacle_max.y >= max_bound.y || obstacle_max.z >= max_bound.z) {
        min_bound = glm::min(obstacle_min - glm::vec3(estimator.voxel_size), min_bound);
        max_bound = glm::max(obstacle_max + glm::vec3(estimator.voxel_size), max_bound);
        bound_changed = true;
      }
    }
  }
  for (const auto& tree_entity : *tree_entities) {
    const auto tree = scene->GetOrSetPrivateComponent<Tree>(tree_entity).lock();
    const auto global_transform = scene->GetDataComponent<GlobalTransform>(tree_entity).value;
    const auto& shoot_skeleton = tree->shoot_model.PeekShootSkeleton();
    glm::vec3 current_min_bound(std::numeric_limits<float>::max());
    glm::vec3 current_max_bound(std::numeric_limits<float>::lowest());
    bool has_finite_position = false;
    for (const auto node_handle : shoot_skeleton.PeekSortedNodeList()) {
      const glm::vec3 world_position =
          global_transform * glm::vec4(shoot_skeleton.PeekNode(node_handle).info.global_position, 1.0f);
      if (!std::isfinite(world_position.x) || !std::isfinite(world_position.y) ||
          !std::isfinite(world_position.z))
        continue;
      current_min_bound = glm::min(current_min_bound, world_position);
      current_max_bound = glm::max(current_max_bound, world_position);
      has_finite_position = true;
    }
    if (has_finite_position &&
        (current_min_bound.x <= min_bound.x || current_min_bound.y <= min_bound.y ||
         current_min_bound.z <= min_bound.z || current_max_bound.x >= max_bound.x ||
         current_max_bound.y >= max_bound.y || current_max_bound.z >= max_bound.z)) {
      min_bound = glm::min(current_min_bound - glm::vec3(1.0f, 0.1f, 1.0f), min_bound);
      max_bound = glm::max(current_max_bound + glm::vec3(1.0f), max_bound);
      bound_changed = true;
    }
  }
  if (bound_changed)
    estimator.voxel_grid.Initialize(estimator.voxel_size, min_bound, max_bound);
  estimator.voxel_grid.Reset();
  for (const auto& tree_entity : *tree_entities) {
    const auto tree = scene->GetOrSetPrivateComponent<Tree>(tree_entity).lock();
    tree->RegisterVoxel();
  }
  for (const auto& obstacle : growth_obstacles) {
    estimator.AddBoxObstacle(obstacle.min_bound, obstacle.max_bound, obstacle.shadow, obstacle.biomass,
                             obstacle.entity_index);
  }

  estimator.LightPropagation(eco_sys_lab_layer->simulation_settings);
}

void eco_sys_lab_package::DeserializeClimate(const YAML::Node& in, Climate& target) {
  target.climate_descriptor_ref.Load("climate_descriptor_ref", in);
}
