#include "ImGuiLayer.hpp"
#include "PyEcoSysLab.hpp"
#include "DsColliders.hpp"
#include "EcoSysLabSerializationAdapters.hpp"
#include "PyEvoEngine.hpp"
#include "Resources.hpp"
#include "Serialization.hpp"

#if DATASET_GENERATION_PACKAGE
#  include "DatasetGenerationSerializationAdapters.hpp"
#endif

#ifdef ECOSYSLAB_PACKAGE
namespace py = pybind11;
using namespace py_eco_sys_lab_package;
void register_classes() {
#  ifdef ECOSYSLAB_PACKAGE
  auto& application = PyEvoEngine::GetRuntime().GetApplication();
  application.RegisterPrivateComponent<ObjectRotator>("ObjectRotator");
  application.RegisterPrivateComponent<Physics2DDemo>("Physics2DDemo");
  application.RegisterPrivateComponent<ParticlePhysics2DDemo>("ParticlePhysics2DDemo");
  application.RegisterPrivateComponent<TreePointCloudScanner>("TreePointCloudScanner");
  Serialization::RegisterSerializationHandler<ObjectRotator>(SerializeObjectRotator, DeserializeObjectRotator, {},
                                                             "ObjectRotator");
  Serialization::RegisterSerializationHandler<TreePointCloudScanner>(
      SerializeTreePointCloudScanner, DeserializeTreePointCloudScanner, {}, "TreePointCloudScanner");
#  endif
}

void push_layers(const bool enable_window_layer, const bool enable_editor_layer) {
  ApplicationContext::Get().PushLayer<RenderLayer>("Render Layer");
  if (enable_window_layer)
    ApplicationContext::Get().PushLayer<WindowLayer>("Window Layer");
  if (enable_window_layer && enable_editor_layer) {
    ApplicationContext::Get().PushLayer<ImGuiLayer>("ImGui Layer");
    ApplicationContext::Get().PushLayer<EditorLayer>("Editor Layer");
  }
  ApplicationContext::Get().PushLayer<EcoSysLabLayer>("EcoSysLab Layer");
}

std::filesystem::path get_default_project_path() {
  std::filesystem::path resource_folder_path("../../../../../Resources");
  if (!std::filesystem::exists(resource_folder_path)) {
    resource_folder_path = "../../../../Resources";
  }
  if (!std::filesystem::exists(resource_folder_path)) {
    resource_folder_path = "../../../Resources";
  }
  if (!std::filesystem::exists(resource_folder_path)) {
    resource_folder_path = "../../Resources";
  }
  if (!std::filesystem::exists(resource_folder_path)) {
    resource_folder_path = "../Resources";
  }
  resource_folder_path = std::filesystem::absolute(resource_folder_path);

  return resource_folder_path / "EcoSysLabProject" / "test.eveproj";
}

void engine_run_windowless(const std::filesystem::path& project_path) {
  if (std::filesystem::path(project_path).extension().string() != ".eveproj") {
    EVOENGINE_ERROR("Project path doesn't point to a valid project!");
    return;
  }
  register_classes();
  push_layers(false, false);
  ApplicationInitializationSettings application_info{};
  application_info.project_path = project_path;
  ApplicationContext::Get().Initialize(application_info);
  const auto new_scene = std::dynamic_pointer_cast<Scene>(ProjectManager::GetOrCreateAsset("./PlayGround.evescene"));
  ProjectManager::SetStartScene(new_scene);

  ApplicationContext::Get().Start();
}

void engine_run(const std::filesystem::path& project_path) {
  if (!project_path.empty()) {
    if (std::filesystem::path(project_path).extension().string() != ".eveproj") {
      EVOENGINE_ERROR("Project path doesn't point to a valid project!");
      return;
    }
  }
  register_classes();
  push_layers(true, false);
  ApplicationInitializationSettings application_info{};
  application_info.project_path = project_path;
  ApplicationContext::Get().Initialize(application_info);
  ApplicationContext::Get().Start();
}

void engine_run_with_editor(const std::filesystem::path& project_path) {
  if (!project_path.empty()) {
    if (std::filesystem::path(project_path).extension().string() != ".eveproj") {
      EVOENGINE_ERROR("Project path doesn't point to a valid project!");
      return;
    }
  }
  register_classes();
  push_layers(true, true);
  ApplicationInitializationSettings application_info{};
  application_info.project_path = project_path;
  ApplicationContext::Get().Initialize(application_info);
  ApplicationContext::Get().Start();
}

void engine_loop() {
  ApplicationContext::Get().Loop();
}

void engine_terminate() {
  ApplicationContext::Get().Terminate();
}
void scene_capture(const float pos_x, const float pos_y, const float pos_z, const float angle_x, const float angle_y,
                   const float angle_z, const int resolution_x, const int resolution_y, bool white_background,
                   const std::string& output_path) {
  if (resolution_x <= 0 || resolution_y <= 0) {
    EVOENGINE_ERROR("Resolution error!");
    return;
  }

  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene) {
    EVOENGINE_ERROR("No active scene!");
    return;
  }
  auto main_camera = scene->main_camera.Get<Camera>();
  Entity main_camera_entity;
  bool temp_camera = false;
  if (!main_camera) {
    main_camera_entity = scene->CreateEntity("Main Camera");
    main_camera = scene->GetOrSetPrivateComponent<Camera>(main_camera_entity).lock();
    scene->main_camera = main_camera;
    temp_camera = true;
  } else {
    main_camera_entity = main_camera->GetOwner();
  }
  auto global_transform = scene->GetDataComponent<GlobalTransform>(main_camera_entity);
  const auto original_transform = global_transform;
  global_transform.SetPosition({pos_x, pos_y, pos_z});
  global_transform.SetEulerRotation(glm::radians(glm::vec3(angle_x, angle_y, angle_z)));
  scene->SetDataComponent(main_camera_entity, global_transform);
  main_camera->Resize({resolution_x, resolution_y});
  const auto use_clear_color = main_camera->camera_settings.use_clear_color;
  const auto clear_color = main_camera->camera_settings.clear_color;
  if (white_background) {
    main_camera->camera_settings.use_clear_color = true;
    main_camera->camera_settings.clear_color = glm::vec4(1, 1, 1, 1);
  }
  ApplicationContext::Get().Loop();
  main_camera->GetRenderTexture()->StoreToPng(output_path);
  if (temp_camera) {
    scene->DeleteEntity(main_camera_entity);
  } else {
    scene->SetDataComponent(main_camera_entity, original_transform);
    if (white_background) {
      main_camera->camera_settings.use_clear_color = use_clear_color;
      main_camera->camera_settings.clear_color = clear_color;
    }
  }

  EVOENGINE_LOG("Exported image to " + output_path);
}

Entity import_tree_point_cloud(const std::string& yaml_path) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const auto ret_val = scene->CreateEntity("TreeStructor");
  const auto tree_point_cloud = scene->GetOrSetPrivateComponent<TreeStructor>(ret_val).lock();
  tree_point_cloud->ImportGraph(yaml_path);
  return ret_val;
}

void tree_structor(const std::filesystem::path& yaml_path, const float import_scale_factor,
                   const ConnectivityGraphSettings& connectivity_graph_settings,
                   const ReconstructionSettings& reconstruction_settings,
                   const DatasetGenerator::TreeDataGenerationParameters& tree_data_generation_parameters) {
  if (!std::filesystem::exists(yaml_path)) {
    EVOENGINE_ERROR("Incorrect yaml path!")
    return;
  }
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const auto temp_entity = scene->CreateEntity("Temp");
  const auto tree_structor = scene->GetOrSetPrivateComponent<TreeStructor>(temp_entity).lock();
  if (!tree_data_generation_parameters.tree_descriptor_path.empty()) {
    const auto actual_tree_descriptor = tree_data_generation_parameters.GetActualTreeDescriptor();
    tree_structor->tree_descriptor_ref = actual_tree_descriptor;
  }
  tree_structor->connectivity_graph_settings = connectivity_graph_settings;
  tree_structor->reconstruction_settings = reconstruction_settings;
  tree_structor->ImportGraph(yaml_path, import_scale_factor);
  tree_structor->EstablishConnectivityGraph();
  tree_structor->BuildSkeletons();

  if (tree_data_generation_parameters.export_mesh) {
    tree_structor->ExportForestObj(
        tree_data_generation_parameters.tree_mesh_generator_settings,
        tree_data_generation_parameters.output_folder / (tree_data_generation_parameters.output_file_name + ".obj"));
  }
  if (tree_data_generation_parameters.export_statistics) {
    tree_structor->ExportForestStatistics(tree_data_generation_parameters.output_folder /
                                          (tree_data_generation_parameters.output_file_name + ".yml"));
  }
  if (tree_data_generation_parameters.export_flow_graph) {
    tree_structor->ExportFlowGraphs(tree_data_generation_parameters.output_folder /
                                    (tree_data_generation_parameters.output_file_name + "_flows.yml"));
  }
  if (tree_data_generation_parameters.export_node_graph) {
    tree_structor->ExportNodeGraphs(tree_data_generation_parameters.output_folder /
                                    (tree_data_generation_parameters.output_file_name + "_nodes.yml"));
  }
  scene->DeleteEntity(temp_entity);
}

void yaml_visualization(const std::string& yaml_path, const ConnectivityGraphSettings& connectivity_graph_settings,
                        const ReconstructionSettings& reconstruction_settings,
                        const TreeMeshGeneratorSettings& mesh_generator_settings, const float pos_x, const float pos_y,
                        const float pos_z, const float angle_x, const float angle_y, const float angle_z,
                        const int resolution_x, const int resolution_y, const std::string& output_path) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const auto temp_entity = scene->CreateEntity("Temp");
  const auto tree_point_cloud = scene->GetOrSetPrivateComponent<TreeStructor>(temp_entity).lock();
  tree_point_cloud->connectivity_graph_settings = connectivity_graph_settings;
  tree_point_cloud->reconstruction_settings = reconstruction_settings;
  tree_point_cloud->ImportGraph(yaml_path);
  tree_point_cloud->EstablishConnectivityGraph();
  tree_point_cloud->BuildSkeletons();
  tree_point_cloud->GenerateForest();
  const auto eco_sys_lab_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  eco_sys_lab_layer->GenerateMeshes(mesh_generator_settings);
  scene_capture(pos_x, pos_y, pos_z, angle_x, angle_y, angle_z, resolution_x, resolution_y, true, output_path);
  scene->DeleteEntity(temp_entity);
}

void voxel_space_colonization_tree_data(
    const float radius, const std::string& binvox_path, const std::string& tree_parameters_path, const float delta_time,
    const int iterations, const TreeMeshGeneratorSettings& mesh_generator_settings, bool export_tree_mesh,
    const std::string& tree_mesh_output_path, bool export_tree_io, const std::string& tree_io_output_path,
    bool export_radial_bounding_volume, const std::string& radial_bounding_volume_output_path,
    bool export_radial_bounding_volume_mesh, const std::string& radial_bounding_volume_mesh_output_path) {
  const auto application_status = ApplicationContext::Get().GetApplicationStatus();
  if (!ApplicationContext::Get().GetActiveScene()) {
    EVOENGINE_ERROR("No project!");
    return;
  }
  if (application_status == Application::ExecutionStatus::OnDestroy) {
    EVOENGINE_ERROR("Application is destroyed!");
    return;
  }
  if (application_status == Application::ExecutionStatus::Uninitialized) {
    EVOENGINE_ERROR("Application not uninitialized!");
    return;
  }
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const auto eco_sys_lab_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  if (!eco_sys_lab_layer) {
    EVOENGINE_ERROR("Application doesn't contain EcoSysLab layer!");
    return;
  }
  std::shared_ptr<Soil> soil;
  std::shared_ptr<Climate> climate;

  const std::vector<Entity>* soil_entities = scene->UnsafeGetPrivateComponentOwnersList<Soil>();
  if (soil_entities && !soil_entities->empty()) {
    soil = scene->GetOrSetPrivateComponent<Soil>(soil_entities->at(0)).lock();
  }
  if (!soil) {
    EVOENGINE_ERROR("No soil in scene!");
    return;
  }
  const std::vector<Entity>* climate_entities = scene->UnsafeGetPrivateComponentOwnersList<Climate>();
  if (climate_entities && !climate_entities->empty()) {
    climate = scene->GetOrSetPrivateComponent<Climate>(climate_entities->at(0)).lock();
  }
  if (!climate) {
    EVOENGINE_ERROR("No climate in scene!");
    return;
  }

  const auto temp_entity = scene->CreateEntity("Temp");
  const auto tree = scene->GetOrSetPrivateComponent<Tree>(temp_entity).lock();
  tree->soil = soil;
  tree->climate = climate;
  std::shared_ptr<TreeDescriptor> tree_descriptor;
  if (ProjectManager::IsInAssetsFolder(tree_parameters_path)) {
    tree_descriptor = std::dynamic_pointer_cast<TreeDescriptor>(
        ProjectManager::GetOrCreateAsset(ProjectManager::GetAssetsRelativePath(tree_parameters_path)));
  } else {
    tree_descriptor = AssetManager::CreateTemporaryAsset<TreeDescriptor>();
  }
  tree->tree_descriptor_ref = tree_descriptor;
  auto& occupancy_grid = tree->shoot_model.tree_occupancy_grid;
  VoxelGrid<TreeOccupancyGridBasicData> input_grid{};
  if (tree->ParseBinvox(binvox_path, input_grid, 1.f)) {
    occupancy_grid.Initialize(input_grid, glm::vec3(-radius, 0, -radius), glm::vec3(radius, 2.0f * radius, radius),
                              tree_descriptor->shoot_descriptor.Get<BasicShootDescriptor>()->internode_length,
                              tree->shoot_model.tree_growth_settings.space_colonization_removal_distance_factor,
                              tree->shoot_model.tree_growth_settings.space_colonization_theta,
                              tree->shoot_model.tree_growth_settings.space_colonization_detection_distance_factor);
  }
  tree->shoot_model.tree_growth_settings.use_space_colonization = true;
  tree->shoot_model.tree_growth_settings.space_colonization_auto_resize = false;

  eco_sys_lab_layer->simulation_settings.delta_time = delta_time;

  ApplicationContext::Get().Loop();
  for (int i = 0; i < iterations; i++) {
    eco_sys_lab_layer->Simulate();
  }

  if (export_tree_mesh) {
    tree->ExportObj(tree_mesh_output_path, mesh_generator_settings);
  }
  if (export_tree_io) {
    bool succeed = tree->ExportIoTree(tree_io_output_path);
  }
  if (export_radial_bounding_volume || export_radial_bounding_volume_mesh) {
    const auto rbv = AssetManager::CreateTemporaryAsset<RadialBoundingVolume>();
    tree->ExportRadialBoundingVolume(rbv);
    if (export_radial_bounding_volume) {
      if (!rbv->Export(radial_bounding_volume_output_path)) {
        EVOENGINE_ERROR("Error exporting file!")
      }
    }
    if (export_radial_bounding_volume_mesh) {
      rbv->ExportAsObj(radial_bounding_volume_mesh_output_path);
    }
  }
  scene->DeleteEntity(temp_entity);
}

void rbv_to_obj(const std::string& rbv_path, const std::string& radial_bounding_volume_mesh_output_path) {
  const auto rbv = AssetManager::CreateTemporaryAsset<RadialBoundingVolume>();
  rbv->Import(rbv_path);
  rbv->ExportAsObj(radial_bounding_volume_mesh_output_path);
}

void rbv_space_colonization_tree_data(const std::string& rbv_path, const std::string& tree_parameters_path,
                                      const float delta_time, const int iterations,
                                      const TreeMeshGeneratorSettings& mesh_generator_settings, bool export_tree_mesh,
                                      const std::string& tree_mesh_output_path, bool export_tree_io,
                                      const std::string& tree_io_output_path, bool export_radial_bounding_volume_mesh,
                                      const std::string& radial_bounding_volume_mesh_output_path) {
  const auto application_status = ApplicationContext::Get().GetApplicationStatus();
  if (!ApplicationContext::Get().GetActiveScene()) {
    EVOENGINE_ERROR("No project!");
    return;
  }
  if (application_status == Application::ExecutionStatus::OnDestroy) {
    EVOENGINE_ERROR("Application is destroyed!");
    return;
  }
  if (application_status == Application::ExecutionStatus::Uninitialized) {
    EVOENGINE_ERROR("Application not uninitialized!");
    return;
  }
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const auto eco_sys_lab_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  if (!eco_sys_lab_layer) {
    EVOENGINE_ERROR("Application doesn't contain EcoSysLab layer!");
    return;
  }
  std::shared_ptr<Soil> soil;
  std::shared_ptr<Climate> climate;

  if (const std::vector<Entity>* soil_entities = scene->UnsafeGetPrivateComponentOwnersList<Soil>();
      soil_entities && !soil_entities->empty()) {
    soil = scene->GetOrSetPrivateComponent<Soil>(soil_entities->at(0)).lock();
  }
  if (!soil) {
    EVOENGINE_ERROR("No soil in scene!");
    return;
  }
  if (const std::vector<Entity>* climate_entities = scene->UnsafeGetPrivateComponentOwnersList<Climate>();
      climate_entities && !climate_entities->empty()) {
    climate = scene->GetOrSetPrivateComponent<Climate>(climate_entities->at(0)).lock();
  }
  if (!climate) {
    EVOENGINE_ERROR("No climate in scene!");
    return;
  }

  const auto temp_entity = scene->CreateEntity("Temp");
  const auto tree = scene->GetOrSetPrivateComponent<Tree>(temp_entity).lock();
  tree->soil = soil;
  tree->climate = climate;
  std::shared_ptr<TreeDescriptor> tree_descriptor;
  if (ProjectManager::IsInAssetsFolder(tree_parameters_path)) {
    tree_descriptor = std::dynamic_pointer_cast<TreeDescriptor>(
        ProjectManager::GetOrCreateAsset(ProjectManager::GetAssetsRelativePath(tree_parameters_path)));
  } else {
    tree_descriptor = AssetManager::CreateTemporaryAsset<TreeDescriptor>();
  }
  tree->tree_descriptor_ref = tree_descriptor;
  auto& occupancy_grid = tree->shoot_model.tree_occupancy_grid;
  const auto rbv = AssetManager::CreateTemporaryAsset<RadialBoundingVolume>();
  rbv->Import(rbv_path);

  occupancy_grid.Initialize(rbv, glm::vec3(-rbv->m_maxRadius, 0, -rbv->m_maxRadius),
                            glm::vec3(rbv->m_maxRadius, 2.0f * rbv->m_maxRadius, rbv->m_maxRadius),
                            tree_descriptor->shoot_descriptor.Get<BasicShootDescriptor>()->internode_length,
                            tree->shoot_model.tree_growth_settings.space_colonization_removal_distance_factor,
                            tree->shoot_model.tree_growth_settings.space_colonization_theta,
                            tree->shoot_model.tree_growth_settings.space_colonization_detection_distance_factor);

  tree->shoot_model.tree_growth_settings.use_space_colonization = true;
  tree->shoot_model.tree_growth_settings.space_colonization_auto_resize = false;
  ApplicationContext::Get().Loop();
  eco_sys_lab_layer->simulation_settings.delta_time = delta_time;
  for (int i = 0; i < iterations; i++) {
    eco_sys_lab_layer->Simulate();
  }

  if (export_tree_mesh) {
    tree->ExportObj(tree_mesh_output_path, mesh_generator_settings);
  }
  if (export_tree_io) {
    bool succeed = tree->ExportIoTree(tree_io_output_path);
  }
  if (export_radial_bounding_volume_mesh) {
    rbv->ExportAsObj(radial_bounding_volume_mesh_output_path);
  }
  scene->DeleteEntity(temp_entity);
}

void scene_light_settings(const float ambient_light_intensity, const float directional_light_intensity) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  scene->environment.ambient_light_intensity = ambient_light_intensity;
  const auto directional_light_entities = scene->GetPrivateComponentOwnersList<DirectionalLight>();
  for (const auto& directional_light_entity : directional_light_entities) {
    const auto directional_light = scene->GetOrSetPrivateComponent<DirectionalLight>(directional_light_entity).lock();
    directional_light->diffuse_brightness = directional_light_intensity;
  }
}

void generate_tree_data(const TreePointCloudCircularCaptureSettings& capture_settings,
                        const DatasetGenerator::CameraCaptureSettings& camera_capture_settings,
                        DatasetGenerator::TreeDataGenerationParameters data_generation_parameters) {
  const auto tree_capture_settings = std::make_shared<TreePointCloudCircularCaptureSettings>();
  *tree_capture_settings = capture_settings;
  data_generation_parameters.camera_capture_settings.resize(1);
  data_generation_parameters.camera_capture_settings[0] = camera_capture_settings;
  data_generation_parameters.point_cloud_capture_settings = tree_capture_settings;
  DatasetGenerator::GenerateDataForTree(data_generation_parameters);
}

void generate_tree_growth_data(const DatasetGenerator::CameraCaptureSettings& camera_capture_settings,
                               DatasetGenerator::TreeDataGenerationParameters data_generation_parameters) {
  data_generation_parameters.camera_capture_settings.resize(1);
  data_generation_parameters.camera_capture_settings[0] = camera_capture_settings;
  DatasetGenerator::GenerateTreeGrowthData(data_generation_parameters);
}

void prepare_tree_scene(const DatasetGenerator::TreeDataGenerationParameters& data_generation_parameters,
                        const bool clear_existing_trees, const std::filesystem::path& soil_descriptor_path) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene) {
    EVOENGINE_ERROR("No active EcoSysLab scene!")
    return;
  }

  const auto soil_entities = scene->UnsafeGetPrivateComponentOwnersList<Soil>();
  if (soil_entities && !soil_entities->empty()) {
    const auto soil = scene->GetOrSetPrivateComponent<Soil>(soil_entities->at(0)).lock();
    const auto soil_descriptor = std::dynamic_pointer_cast<SoilDescriptor>(
        ProjectManager::GetOrCreateAsset(soil_descriptor_path.empty() ? std::filesystem::path("Soils") /
                                                                            "PlayGround.soil"
                                                                      : soil_descriptor_path));
    soil->soil_descriptor_ref = soil_descriptor;
    if (data_generation_parameters.generate_ground_mesh) {
      if (const auto height_field = soil_descriptor->height_field.Get<HeightField>()) {
        std::mt19937 random_engine(static_cast<uint32_t>(data_generation_parameters.seed));
        std::uniform_real_distribution<float> offset_distribution(0.0f, 99999.0f);
        height_field->position_offset = {offset_distribution(random_engine), offset_distribution(random_engine)};
      }
      soil->GenerateMesh(0.0f, 0.0f);
    }
  }

  if (clear_existing_trees) {
    const auto tree_entities = scene->UnsafeGetPrivateComponentOwnersList<Tree>();
    if (!tree_entities) {
      std::filesystem::create_directories(data_generation_parameters.output_folder);
      return;
    }
    const auto copied_tree_entities = *tree_entities;
    for (const auto& tree_entity : copied_tree_entities) {
      if (scene->IsEntityValid(tree_entity)) {
        scene->DeleteEntity(tree_entity);
      }
    }
  }
  std::filesystem::create_directories(data_generation_parameters.output_folder);
}

Entity create_tree(const DatasetGenerator::TreeDataGenerationParameters& data_generation_parameters, const float x,
                   const float z, const int seed, const std::string& name, const float scale) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene) {
    EVOENGINE_ERROR("No active EcoSysLab scene!")
    return {};
  }
  const auto tree_entity = scene->CreateEntity(name.empty() ? "Tree" : name);
  const auto tree = scene->GetOrSetPrivateComponent<Tree>(tree_entity).lock();
  tree->tree_descriptor_ref = data_generation_parameters.GetActualTreeDescriptor();
  tree->shoot_model.tree_growth_settings.use_space_colonization = false;
  tree->shoot_model.seed = seed;

  auto tree_position = glm::vec3(x, 0.0f, z);
  if (const auto soil = EcoSysLabLayer::FindSoil().lock()) {
    if (const auto soil_descriptor = soil->soil_descriptor_ref.Get<SoilDescriptor>()) {
      if (const auto height_field = soil_descriptor->height_field.Get<HeightField>()) {
        tree_position.y = height_field->GetValue({x, z}) - 0.01f;
      }
    }
  }
  GlobalTransform gt{};
  gt.SetPosition(tree_position);
  gt.SetScale(glm::vec3(scale));
  scene->SetDataComponent(tree_entity, gt);
  return tree_entity;
}

Entity create_building_box(const int object_id, const std::string& name, const float x, const float z,
                           const float width, const float height, const float depth) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene || object_id < 1001) {
    EVOENGINE_ERROR("Building object ID must be at least 1001.")
    return {};
  }

  const auto entity = scene->CreateEntity("ID" + std::to_string(object_id) + "_" + name);
  const auto renderer = scene->GetOrSetPrivateComponent<MeshRenderer>(entity).lock();
  renderer->mesh = Resources::GetInstance().GetPrimitives().cube;
  const auto material = AssetManager::CreateTemporaryAsset<Material>();
  material->material_properties.albedo_color = glm::vec3(0.55f, 0.58f, 0.62f);
  material->material_properties.roughness = 0.85f;
  renderer->material = material;
  const auto growth_obstacle = scene->GetOrSetPrivateComponent<DsBoxCollider>(entity).lock();
  growth_obstacle->scale = glm::vec3(0.5f);
  growth_obstacle->affect_tree_growth = true;
  growth_obstacle->tree_growth_shadow = 1.0f;
  growth_obstacle->tree_growth_biomass = 1.0f;

  float ground_height = 0.0f;
  if (const auto soil = EcoSysLabLayer::FindSoil().lock()) {
    if (const auto soil_descriptor = soil->soil_descriptor_ref.Get<SoilDescriptor>()) {
      if (const auto height_field = soil_descriptor->height_field.Get<HeightField>()) {
        ground_height = height_field->GetValue({x, z});
      }
    }
  }
  GlobalTransform transform{};
  transform.SetPosition({x, ground_height + height * 0.5f, z});
  transform.SetScale({width, height, depth});
  scene->SetDataComponent(entity, transform);
  return entity;
}

glm::vec3 get_entity_position(const Entity& entity) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene || !scene->IsEntityValid(entity)) {
    EVOENGINE_ERROR("Invalid entity.")
    return {};
  }
  return scene->GetDataComponent<GlobalTransform>(entity).GetPosition();
}

float lower_tree_by_height_ratio(const Entity& tree_entity, const float ratio) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene || !scene->IsEntityValid(tree_entity) || ratio < 0.0f) {
    EVOENGINE_ERROR("Invalid tree entity or height ratio.")
    return 0.0f;
  }
  const auto tree = scene->GetOrSetPrivateComponent<Tree>(tree_entity).lock();
  if (!tree) {
    EVOENGINE_ERROR("Entity doesn't contain Tree.")
    return 0.0f;
  }
  auto& skeleton = tree->shoot_model.RefShootSkeleton();
  skeleton.CalculateMinMax();
  auto transform = scene->GetDataComponent<GlobalTransform>(tree_entity);
  const float height = (skeleton.max.y - skeleton.min.y) * glm::abs(transform.GetScale().y);
  const float depth = height * ratio;
  transform.SetPosition(transform.GetPosition() - glm::vec3(0.0f, depth, 0.0f));
  scene->SetDataComponent(tree_entity, transform);
  return depth;
}

float scale_tree_to_height(const Entity& tree_entity, const float target_height) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene || !scene->IsEntityValid(tree_entity) || target_height <= 0.0f) {
    EVOENGINE_ERROR("Invalid tree entity or target height.")
    return 1.0f;
  }
  const auto tree = scene->GetOrSetPrivateComponent<Tree>(tree_entity).lock();
  if (!tree) {
    EVOENGINE_ERROR("Entity doesn't contain Tree.")
    return 1.0f;
  }
  auto& skeleton = tree->shoot_model.RefShootSkeleton();
  skeleton.CalculateMinMax();
  auto transform = scene->GetDataComponent<GlobalTransform>(tree_entity);
  const float current_height = (skeleton.max.y - skeleton.min.y) * glm::abs(transform.GetScale().y);
  if (current_height <= glm::epsilon<float>())
    return 1.0f;
  const float scale_factor = target_height / current_height;
  transform.SetScale(transform.GetScale() * scale_factor);
  scene->SetDataComponent(tree_entity, transform);
  return scale_factor;
}

bool export_ground_mesh(const std::filesystem::path& output_path) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const auto soil = EcoSysLabLayer::FindSoil().lock();
  if (!scene || !soil) {
    EVOENGINE_ERROR("Missing active scene or soil.")
    return false;
  }

  Entity ground_entity{};
  for (const auto& child : scene->GetChildren(soil->GetOwner())) {
    if (scene->GetEntityName(child) == "Ground Mesh" && scene->HasPrivateComponent<MeshRenderer>(child)) {
      ground_entity = child;
      break;
    }
  }
  if (!scene->IsEntityValid(ground_entity)) {
    EVOENGINE_ERROR("Ground Mesh entity was not found.")
    return false;
  }

  const auto renderer = scene->GetOrSetPrivateComponent<MeshRenderer>(ground_entity).lock();
  const auto mesh = renderer ? renderer->mesh.Get<Mesh>() : nullptr;
  if (!mesh || mesh->PeekVertices().empty() || mesh->PeekTriangles().empty()) {
    EVOENGINE_ERROR("Ground Mesh has no geometry.")
    return false;
  }

  if (!output_path.parent_path().empty()) {
    std::filesystem::create_directories(output_path.parent_path());
  }
  std::ofstream output(output_path, std::ofstream::out | std::ofstream::trunc);
  if (!output.is_open()) {
    EVOENGINE_ERROR("Could not open ground OBJ output path.")
    return false;
  }

  const auto transform = scene->GetDataComponent<GlobalTransform>(ground_entity).value;
  output << "# EcoSysLab ground mesh\n"
         << "o ID1000_Ground\n";
  for (const auto& vertex : mesh->PeekVertices()) {
    const auto position = transform * glm::vec4(vertex.position, 1.0f);
    output << "v " << position.x << " " << position.y << " " << position.z << "\n";
  }
  for (const auto& triangle : mesh->PeekTriangles()) {
    output << "f " << triangle.x + 1 << " " << triangle.y + 1 << " " << triangle.z + 1 << "\n";
  }
  return true;
}

bool prepare_tree_growth_step(const SimulationSettings& simulation_settings, const float time) {
  const auto eco_sys_lab_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  const auto climate = EcoSysLabLayer::FindClimate().lock();
  const auto soil = EcoSysLabLayer::FindSoil().lock();
  if (!eco_sys_lab_layer || !climate || !soil) {
    EVOENGINE_ERROR("Missing EcoSysLab layer, climate, or soil.")
    return false;
  }
  eco_sys_lab_layer->simulation_settings = simulation_settings;
  climate->climate_model.time = time;
  if (simulation_settings.soil_simulation) {
    soil->soil_model.Irrigation();
    soil->soil_model.Step();
  }
  climate->PrepareForGrowth();
  return true;
}

py::dict sample_tree_growth_environment(const float x, const float y, const float z) {
  py::dict result;
  const auto climate = EcoSysLabLayer::FindClimate().lock();
  if (!climate) {
    EVOENGINE_ERROR("Missing climate.")
    return result;
  }
  const auto& grid = climate->climate_model.environment_grid;
  const auto position = glm::vec3(x, y, z);
  const auto coordinate = grid.voxel_grid.GetCoordinate(position);
  const auto& voxel = grid.voxel_grid.Peek(coordinate);
  result["light_intensity"] = voxel.light_intensity;
  result["light_direction"] =
      py::make_tuple(voxel.light_direction.x, voxel.light_direction.y, voxel.light_direction.z);
  result["self_shadow"] = voxel.self_shadow;
  result["total_biomass"] = voxel.total_biomass;
  result["registration_count"] = voxel.internode_voxel_registrations.size();
  return result;
}

bool grow_tree(const Entity& tree_entity, const SimulationSettings& simulation_settings, const bool pruning) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene || !scene->IsEntityValid(tree_entity)) {
    EVOENGINE_ERROR("Invalid tree entity.")
    return false;
  }
  const auto tree = scene->GetOrSetPrivateComponent<Tree>(tree_entity).lock();
  return tree && tree->TryGrow(simulation_settings, -1, pruning);
}

void grow_tree_scene_step(const std::vector<Entity>& tree_entities, const SimulationSettings& simulation_settings,
                          const float time, const bool pruning) {
  if (!prepare_tree_growth_step(simulation_settings, time)) {
    return;
  }
  for (const auto& tree_entity : tree_entities) {
    grow_tree(tree_entity, simulation_settings, pruning);
  }
}

void generate_tree_meshes(const TreeMeshGeneratorSettings& mesh_generator_settings) {
  const auto eco_sys_lab_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  if (!eco_sys_lab_layer) {
    EVOENGINE_ERROR("Application doesn't contain EcoSysLab layer!")
    return;
  }
  eco_sys_lab_layer->GenerateMeshes(mesh_generator_settings);
  ApplicationContext::Get().Loop();
  ApplicationContext::Get().Loop();
}

void export_all_trees(const std::filesystem::path& output_path) {
  const auto eco_sys_lab_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  if (!eco_sys_lab_layer) {
    EVOENGINE_ERROR("Application doesn't contain EcoSysLab layer!")
    return;
  }
  eco_sys_lab_layer->ExportAllTrees(output_path);
}

bool export_tree(const Entity& tree_entity, const TreeMeshGeneratorSettings& mesh_generator_settings,
                 const std::filesystem::path& output_path) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene || !scene->IsEntityValid(tree_entity)) {
    EVOENGINE_ERROR("Invalid tree entity.")
    return false;
  }
  const auto tree = scene->GetOrSetPrivateComponent<Tree>(tree_entity).lock();
  if (!tree) {
    EVOENGINE_ERROR("Entity doesn't contain Tree.")
    return false;
  }
  tree->ExportObj(output_path, mesh_generator_settings);
  return true;
}

void scan_tree_point_cloud(const TreePointCloudCircularCaptureSettings& capture_settings,
                           const TreePointCloudPointSettings& point_settings,
                           const TreeMeshGeneratorSettings& mesh_generator_settings,
                           const std::filesystem::path& output_path) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene) {
    EVOENGINE_ERROR("No active EcoSysLab scene!")
    return;
  }
  const auto scanner_entity = scene->CreateEntity("Scanner");
  const auto scanner = scene->GetOrSetPrivateComponent<TreePointCloudScanner>(scanner_entity).lock();
  auto point_cloud_capture_settings = std::make_shared<TreePointCloudCircularCaptureSettings>();
  *point_cloud_capture_settings = capture_settings;
  scanner->point_settings = point_settings;
  ApplicationContext::Get().Loop();
  ApplicationContext::Get().Loop();
  scanner->Capture(mesh_generator_settings, output_path, point_cloud_capture_settings);
  scene->DeleteEntity(scanner_entity);
}

void scan_tree_point_cloud_spherical(const TreePointCloudSphericalCaptureSettings& capture_settings,
                                     const TreePointCloudPointSettings& point_settings,
                                     const TreeMeshGeneratorSettings& mesh_generator_settings,
                                     const std::filesystem::path& output_path) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene) {
    EVOENGINE_ERROR("No active EcoSysLab scene!")
    return;
  }
  const auto scanner_entity = scene->CreateEntity("Spherical TLS Scanner");
  const auto scanner = scene->GetOrSetPrivateComponent<TreePointCloudScanner>(scanner_entity).lock();
  auto point_cloud_capture_settings = std::make_shared<TreePointCloudSphericalCaptureSettings>(capture_settings);
  scanner->point_settings = point_settings;
  ApplicationContext::Get().Loop();
  ApplicationContext::Get().Loop();
  scanner->Capture(mesh_generator_settings, output_path, point_cloud_capture_settings);
  scene->DeleteEntity(scanner_entity);
}

void capture_tree_scene(const DatasetGenerator::CameraCaptureSettings& camera_capture_settings,
                        const std::filesystem::path& color_output_path, const std::filesystem::path& depth_output_path,
                        const float max_depth) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  if (!scene) {
    EVOENGINE_ERROR("No active EcoSysLab scene!")
    return;
  }

  const auto camera_entity = scene->CreateEntity("Capture Camera");
  const auto camera = scene->GetOrSetPrivateComponent<Camera>(camera_entity).lock();
  camera->camera_settings = camera_capture_settings.camera_settings;
  camera->post_processing_stack_ref.Get<PostProcessingStack>()->enable_bloom = false;
  camera->Resize(camera_capture_settings.render_resolution);
  camera->SetRequireRendering(true);

  GlobalTransform camera_global_transform{};
  const auto pivot_rotation = glm::quat(glm::radians(camera_capture_settings.pivot_euler_rotation));
  camera_global_transform.SetPosition(camera_capture_settings.pivot_position +
                                      glm::rotate(pivot_rotation, camera_capture_settings.anchor_position));
  camera_global_transform.SetRotation(pivot_rotation * glm::quat(glm::radians(camera_capture_settings.anchor_rotation)));
  scene->SetDataComponent(camera_entity, camera_global_transform);
  ApplicationContext::Get().Loop();

  if (!color_output_path.empty()) {
    camera->GetRenderTexture()->StoreToPng(color_output_path, camera_capture_settings.output_resolution.x,
                                           camera_capture_settings.output_resolution.y);
  }
  if (!depth_output_path.empty()) {
    camera->GetRenderTexture()->StoreLinearDepthToPng(
        depth_output_path, camera->camera_settings.near_distance, camera->camera_settings.far_distance, max_depth,
        camera_capture_settings.output_resolution.x, camera_capture_settings.output_resolution.y);
  }
  scene->DeleteEntity(camera_entity);
}

PYBIND11_MAKE_OPAQUE(std::vector<int>)

PYBIND11_MODULE(PyEcoSysLab, m) {
  m.doc() = "PyEcoSysLab";  // optional module docstring
  PyEcoSysLab::Initialize(m);
  m.def("tree_structor", &tree_structor, "Reconstruct tree(s) and export meshes");
  m.def("scene_capture", &scene_capture, "Capture current scene");
  m.def("yaml_visualization", &yaml_visualization, "Reconstruct tree(s) and capture an image for visualization");
  m.def("voxel_space_colonization_tree_data", &voxel_space_colonization_tree_data,
        "Grow a tree in voxel space and export data");
  m.def("rbv_space_colonization_tree_data", &rbv_space_colonization_tree_data, "Grow a tree in RBV and export data");
  m.def("rbv_to_obj", &rbv_to_obj, "Convert RBV to 3D model (OBJ)");

  m.def("generate_tree_data", &generate_tree_data, "Generate data for single tree");
  m.def("generate_tree_growth_data", &generate_tree_growth_data, "Generate data for single tree growth");
  m.def("prepare_tree_scene", &prepare_tree_scene, py::arg("data_generation_parameters"),
        py::arg("clear_existing_trees") = true, py::arg("soil_descriptor_path") = std::filesystem::path("Soils") /
                                                                                  "PlayGround.soil");
  m.def("create_tree", &create_tree, py::arg("data_generation_parameters"), py::arg("x"), py::arg("z"),
        py::arg("seed"), py::arg("name") = "Tree", py::arg("scale") = 1.0f);
  m.def("create_building_box", &create_building_box, py::arg("object_id"), py::arg("name"), py::arg("x"),
        py::arg("z"), py::arg("width"), py::arg("height"), py::arg("depth"));
  m.def("get_entity_position", &get_entity_position, py::arg("entity"));
  m.def("scale_tree_to_height", &scale_tree_to_height, py::arg("tree_entity"), py::arg("target_height"));
  m.def("lower_tree_by_height_ratio", &lower_tree_by_height_ratio, py::arg("tree_entity"), py::arg("ratio"));
  m.def("export_ground_mesh", &export_ground_mesh, py::arg("output_path"));
  m.def("prepare_tree_growth_step", &prepare_tree_growth_step, py::arg("simulation_settings"), py::arg("time"));
  m.def("sample_tree_growth_environment", &sample_tree_growth_environment, py::arg("x"), py::arg("y"),
        py::arg("z"));
  m.def("grow_tree", &grow_tree, py::arg("tree_entity"), py::arg("simulation_settings"), py::arg("pruning") = true);
  m.def("grow_tree_scene_step", &grow_tree_scene_step, py::arg("tree_entities"), py::arg("simulation_settings"),
        py::arg("time"), py::arg("pruning") = true);
  m.def("generate_tree_meshes", &generate_tree_meshes, py::arg("mesh_generator_settings"));
  m.def("export_all_trees", &export_all_trees, py::arg("output_path"));
  m.def("export_tree", &export_tree, py::arg("tree_entity"), py::arg("mesh_generator_settings"),
        py::arg("output_path"));
  m.def("scan_tree_point_cloud", &scan_tree_point_cloud, py::arg("capture_settings"), py::arg("point_settings"),
        py::arg("mesh_generator_settings"), py::arg("output_path"));
  m.def("scan_tree_point_cloud", &scan_tree_point_cloud_spherical, py::arg("capture_settings"),
        py::arg("point_settings"), py::arg("mesh_generator_settings"), py::arg("output_path"));
  m.def("capture_tree_scene", &capture_tree_scene, py::arg("camera_capture_settings"), py::arg("color_output_path"),
        py::arg("depth_output_path"), py::arg("max_depth"));
  m.def("scene_light_settings", &scene_light_settings, "Configure scene lighting");
}
#endif
