#include "DatasetGenerationSerializationAdapters.hpp"

#include "DatasetGenerationInspectionAdapters.hpp"

#include "CpuRayTracer.hpp"
#include "EcoSysLabLayer.hpp"
#include "PointCloud.hpp"
#include "Sorghum.hpp"
#include "Tinyply.hpp"
#include "TreePointCloudScanner.hpp"

#include <iomanip>
#include <unordered_set>
#ifdef CUDA_MODULE_SERVICE
#  include "CUDAModule.hpp"
#  include "RayTracerLayer.hpp"
#endif
using namespace digital_agriculture_package;
using namespace dataset_generation_package;
bool SorghumPointCloudPointSettings::DrawGui() {
  return false;
}

void SorghumPointCloudPointSettings::Save(const std::string& name, YAML::Emitter& out) const {
}

void SorghumPointCloudPointSettings::Load(const std::string& name, const YAML::Node& in) {
}

bool SorghumPointCloudGridCaptureSettings::DrawGui() {
  bool changed = false;
  if (ImGui::DragInt2("Grid size", &grid_size.x, 1, 0, 100))
    changed = true;
  if (ImGui::DragFloat("Grid distance", &grid_distance, 0.1f, 0.0f, 100.0f))
    changed = true;
  if (ImGui::DragFloat("Step", &step, 0.01f, 0.0f, 0.5f))
    changed = true;
  return changed;
}

void SorghumPointCloudGridCaptureSettings::GenerateSamples(std::vector<PointCloudSample>& point_cloud_samples) {
  const glm::vec2 start_point = glm::vec2((static_cast<float>(grid_size.x) * 0.5f - 0.5f) * grid_distance,
                                          (static_cast<float>(grid_size.y) * 0.5f - 0.5f) * grid_distance);

  const int y_step_size = static_cast<int>(grid_size.y * grid_distance / step);
  const int x_step_size = static_cast<int>(grid_size.x * grid_distance / step);

  point_cloud_samples.resize((grid_size.x * y_step_size + grid_size.y * x_step_size) * drone_sample);
  unsigned start_index = 0;
  for (int i = 0; i < grid_size.x; i++) {
    float x = static_cast<float>(i) * grid_distance;
    for (int step = 0; step < y_step_size; step++) {
      float z = static_cast<float>(step * step);
      const glm::vec3 center = glm::vec3{x, drone_height, z} - glm::vec3(start_point.x, 0, start_point.y);
      Jobs::RunParallelFor(drone_sample, [&](size_t sample_index) {
        auto& sample = point_cloud_samples[drone_sample * (i * y_step_size + step) + sample_index];
        sample.direction = glm::sphericalRand(1.0f);
        sample.direction.y = -glm::abs(sample.direction.y);
        sample.start = center;
      });
    }
  }
  start_index += grid_size.x * y_step_size * drone_sample;
  for (int i = 0; i < grid_size.y; i++) {
    float z = static_cast<float>(i) * grid_distance;
    for (int step = 0; step < x_step_size; step++) {
      float x = static_cast<float>(step * step);
      const glm::vec3 center = glm::vec3{x, drone_height, z} - glm::vec3(start_point.x, 0, start_point.y);
      Jobs::RunParallelFor(drone_sample, [&](size_t sample_index) {
        auto& sample = point_cloud_samples[start_index + drone_sample * (i * x_step_size + step) + sample_index];
        sample.direction = glm::sphericalRand(1.0f);
        sample.direction.y = -glm::abs(sample.direction.y);
        sample.start = center;
      });
    }
  }
}

bool SorghumPointCloudGridCaptureSettings::SampleFilter(const PointCloudSample& sample) {
  return glm::abs(sample.hit_info.position.x) < bounding_box_size &&
         glm::abs(sample.hit_info.position.z) < bounding_box_size;
}

bool SorghumGantryCaptureSettings::DrawGui() {
  bool changed = false;
  if (ImGui::DragInt2("Grid size", &grid_size.x, 1, 0, 100))
    changed = true;
  if (ImGui::DragFloat2("Grid distance", &grid_distance.x, 0.1f, 0.0f, 100.0f))
    changed = true;
  if (ImGui::DragFloat("Step", &step, 0.00001f, 0.0f, 0.5f))
    changed = true;

  return changed;
}

void SorghumGantryCaptureSettings::GenerateSamples(std::vector<PointCloudSample>& point_cloud_samples) {
  const glm::vec2 start_point = glm::vec2(grid_size.x * grid_distance.x, grid_size.y * grid_distance.y) * 0.5f;
  const int x_step_size = static_cast<int>(grid_size.x * grid_distance.x / step);
  const int y_step_size = static_cast<int>(grid_size.y * grid_distance.y / step);

  point_cloud_samples.resize(y_step_size * x_step_size * 2 * scanner_angles.size());
  constexpr auto front = glm::vec3(0, -1, 0);
  const float roll_angle = glm::linearRand(0.0f, 360.0f);
  const auto up = glm::vec3(glm::sin(glm::radians(roll_angle)), 0, glm::cos(glm::radians(roll_angle)));
  Jobs::RunParallelFor(y_step_size * x_step_size, [&](size_t i) {
    const auto x = i / y_step_size;
    const auto y = i % y_step_size;
    const glm::vec3 center = glm::vec3{step * x, 0.f, step * y} - glm::vec3(start_point.x, 0, start_point.y);
    for (int angle_index = 0; angle_index < scanner_angles.size(); angle_index++) {
      auto& sample1 = point_cloud_samples[i * scanner_angles.size() + angle_index];
      const auto& scanner_angle = scanner_angles[angle_index];
      sample1.direction = glm::normalize(glm::rotate(front, glm::radians(scanner_angle), up));
      sample1.start = center - sample1.direction * (sample_height / glm::cos(glm::radians(scanner_angle)));

      auto& sample2 = point_cloud_samples[y_step_size * x_step_size * scanner_angles.size() +
                                          i * scanner_angles.size() + angle_index];
      sample2.direction = glm::normalize(glm::rotate(front, glm::radians(-scanner_angle), up));
      sample2.start = center - sample2.direction * (sample_height / glm::cos(glm::radians(scanner_angle)));
    }
  });
}

bool SorghumGantryCaptureSettings::SampleFilter(const PointCloudSample& sample) {
  return glm::abs(sample.hit_info.position.x) < bounding_box_size &&
         glm::abs(sample.hit_info.position.z) < bounding_box_size;
}

bool SorghumFractionalCoverSettings::DrawGui() {
  bool changed = false;
  changed |= ImGui::DragFloat2("Center", &center.x, 0.05f);
  changed |= ImGui::DragFloat2("Area size", &area_size.x, 0.05f, 0.01f, 10000.f);
  changed |= ImGui::DragInt2("Resolution", &resolution.x, 1.f, 1, 4096);
  changed |= ImGui::DragInt("Samples per pixel axis", &samples_per_pixel_axis, 1.f, 1, 64);
  changed |= ImGui::DragFloat("Scan height", &scan_height, 0.05f);
  return changed;
}

void SorghumFractionalCoverSettings::Save(const std::string& name, YAML::Emitter& out) const {
  out << YAML::Key << name << YAML::Value << YAML::BeginMap;
  out << YAML::Key << "center" << YAML::Value << center;
  out << YAML::Key << "area_size" << YAML::Value << area_size;
  out << YAML::Key << "resolution" << YAML::Value << resolution;
  out << YAML::Key << "samples_per_pixel_axis" << YAML::Value << samples_per_pixel_axis;
  out << YAML::Key << "scan_height" << YAML::Value << scan_height;
  out << YAML::EndMap;
}

void SorghumFractionalCoverSettings::Load(const std::string& name, const YAML::Node& in) {
  if (!in[name])
    return;
  const auto& settings = in[name];
  if (settings["center"])
    center = settings["center"].as<glm::vec2>();
  if (settings["area_size"])
    area_size = settings["area_size"].as<glm::vec2>();
  if (settings["resolution"])
    resolution = settings["resolution"].as<glm::ivec2>();
  if (settings["samples_per_pixel_axis"])
    samples_per_pixel_axis = settings["samples_per_pixel_axis"].as<int>();
  if (settings["scan_height"])
    scan_height = settings["scan_height"].as<float>();
}

void SorghumFractionalCoverSettings::GenerateSamples(std::vector<PointCloudSample>& samples) const {
  if (resolution.x <= 0 || resolution.y <= 0 || samples_per_pixel_axis <= 0 || area_size.x <= 0.f ||
      area_size.y <= 0.f) {
    samples.clear();
    return;
  }
  const size_t pixel_count = static_cast<size_t>(resolution.x) * resolution.y;
  const size_t samples_per_pixel = static_cast<size_t>(samples_per_pixel_axis) * samples_per_pixel_axis;
  samples.resize(pixel_count * samples_per_pixel);
  for (size_t pixel_index = 0; pixel_index < pixel_count; ++pixel_index) {
    const int pixel_x = static_cast<int>(pixel_index % resolution.x);
    const int pixel_y = static_cast<int>(pixel_index / resolution.x);
    for (int sample_y = 0; sample_y < samples_per_pixel_axis; ++sample_y) {
      for (int sample_x = 0; sample_x < samples_per_pixel_axis; ++sample_x) {
        const float u = (static_cast<float>(pixel_x) + (static_cast<float>(sample_x) + 0.5f) / samples_per_pixel_axis) /
                        static_cast<float>(resolution.x);
        const float v = (static_cast<float>(pixel_y) + (static_cast<float>(sample_y) + 0.5f) / samples_per_pixel_axis) /
                        static_cast<float>(resolution.y);
        auto& sample = samples[pixel_index * samples_per_pixel +
                               static_cast<size_t>(sample_y * samples_per_pixel_axis + sample_x)];
        sample.start = glm::vec3(center.x + (u - 0.5f) * area_size.x, scan_height, center.y + (v - 0.5f) * area_size.y);
        sample.direction = glm::vec3(0.f, -1.f, 0.f);
      }
    }
  }
}

void SorghumPointCloudScanner::Scan(const std::shared_ptr<PointCloudCaptureSettings>& capture_settings,
                                    std::vector<glm::vec3>& points, std::vector<int>& leaf_indices,
                                    std::vector<int>& instance_indices, std::vector<int>& type_indices) const {
  const auto render_layer = ApplicationContext::Get().GetLayer<RenderLayer>();

  const auto digital_agriculture_layer = ApplicationContext::Get().GetLayer<EcoSysLabLayer>();
  std::shared_ptr<Soil> soil;
  if (const auto soil_candidate = EcoSysLabLayer::FindSoil(); !soil_candidate.expired())
    soil = soil_candidate.lock();
  Bound plant_bound{};
  std::unordered_map<Handle, std::pair<Handle, int>> leaf_mesh_renderer_handles;
  std::unordered_map<Handle, Handle> stem_mesh_renderer_handles, panicle_mesh_renderer_handles;
  const auto scene = GetScene();
  const std::vector<Entity>* sorghum_entities = scene->UnsafeGetPrivateComponentOwnersList<Sorghum>();
  if (sorghum_entities == nullptr) {
    EVOENGINE_ERROR("No sorghums!");
    return;
  }

  for (const auto& sorghum_entity : *sorghum_entities) {
    if (scene->IsEntityValid(sorghum_entity)) {
      int leaf_index = 0;
      scene->ForEachChild(sorghum_entity, [&](const Entity child) {
        if (scene->GetEntityName(child) == "Leaf Mesh" && scene->HasPrivateComponent<MeshRenderer>(child)) {
          const auto leaf_mesh_renderer = scene->GetOrSetPrivateComponent<MeshRenderer>(child).lock();
          leaf_mesh_renderer_handles.insert(
              {leaf_mesh_renderer->GetHandle(), std::make_pair(sorghum_entity.GetIndex(), leaf_index)});
          leaf_index++;
          const auto global_transform = scene->GetDataComponent<GlobalTransform>(child);
          const auto mesh = leaf_mesh_renderer->mesh.Get<Mesh>();
          plant_bound.min =
              glm::min(plant_bound.min, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().min, 1.0f)));
          plant_bound.max =
              glm::max(plant_bound.max, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().max, 1.0f)));
        } else if (scene->GetEntityName(child) == "Stem Mesh" && scene->HasPrivateComponent<Particles>(child)) {
          const auto stem_mesh_renderer = scene->GetOrSetPrivateComponent<MeshRenderer>(child).lock();
          stem_mesh_renderer_handles.insert({stem_mesh_renderer->GetHandle(), sorghum_entity.GetIndex()});

          const auto global_transform = scene->GetDataComponent<GlobalTransform>(child);
          const auto mesh = stem_mesh_renderer->mesh.Get<Mesh>();
          plant_bound.min =
              glm::min(plant_bound.min, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().min, 1.0f)));
          plant_bound.max =
              glm::max(plant_bound.max, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().max, 1.0f)));
        } else if (scene->GetEntityName(child) == "Panicle Strands" &&
                   scene->HasPrivateComponent<StrandsRenderer>(child)) {
          const auto panicle_mesh_renderer = scene->GetOrSetPrivateComponent<MeshRenderer>(child).lock();
          panicle_mesh_renderer_handles.insert({panicle_mesh_renderer->GetHandle(), sorghum_entity.GetIndex()});

          const auto global_transform = scene->GetDataComponent<GlobalTransform>(child);
          const auto mesh = panicle_mesh_renderer->mesh.Get<Mesh>();
          plant_bound.min =
              glm::min(plant_bound.min, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().min, 1.0f)));
          plant_bound.max =
              glm::max(plant_bound.max, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().max, 1.0f)));
        }
      });
    }
  }

  Handle ground_mesh_renderer_handle = 0;
  if (soil) {
    if (auto soil_entity = soil->GetOwner(); scene->IsEntityValid(soil_entity)) {
      scene->ForEachChild(soil_entity, [&](Entity child) {
        if (scene->GetEntityName(child) == "Ground Mesh" && scene->HasPrivateComponent<MeshRenderer>(child)) {
          ground_mesh_renderer_handle = scene->GetOrSetPrivateComponent<MeshRenderer>(child).lock()->GetHandle();
        }
      });
    }
  }
  std::vector<PointCloudSample> pc_samples;
  capture_settings->GenerateSamples(pc_samples);

  switch (capture_settings->capture_mode) {
    case PointCloudCaptureSettings::CaptureMode::Cpu: {
      /**
       * You may take a look at render instances, to see what it contains. RenderLayer will prepare a RenderInstance
       * every frame that contains all needed information for rendering everything for current scene. It's used in
       * rasterization rendering, and here we also use it for ray tracing. It also detects updates of the scene, like
       * transformation, mesh, material changes.
       */
      std::shared_ptr<RenderInstanceStorage> render_instances{};
      if (render_layer) {
        render_instances = render_layer->GetCurrentRenderInstanceStorage();
      }
      if (!render_instances) {
        render_instances = std::make_shared<RenderInstanceStorage>();
        Bound world_bound;
        render_instances->BuildFromScene({}, ApplicationContext::Get().GetActiveScene(), world_bound);
      }
      CpuRayTracer cpu_ray_tracer;
      /**
       * During this step, the cpu_ray_tracer will scan all MeshRendereres in the scene, and establish TLAS and BLAS
       * based on them.
       */
      cpu_ray_tracer.Initialize(
          render_instances,
          [&](uint32_t, const std::shared_ptr<Mesh>&) {

          },
          [&](const uint32_t node_index, const Entity& entity) {

          });
      cpu_ray_tracer.SamplePointCloud(pc_samples);
    } break;
    case PointCloudCaptureSettings::CaptureMode::Gpu: {
      PointCloud::SampleCurrentScene(pc_samples);
    } break;
  }

  glm::vec3 left_offset = glm::linearRand(-left_random_offset, left_random_offset);
  glm::vec3 right_offset = glm::linearRand(-right_random_offset, right_random_offset);
  for (int sample_index = 0; sample_index < pc_samples.size(); sample_index++) {
    const auto& sample = pc_samples.at(sample_index);
    if (sample.hit_count == 0)
      continue;
    if (!capture_settings->SampleFilter(sample))
      continue;
    auto& position = sample.hit_info.position;
    if (position.x < (plant_bound.min.x - sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.y < (plant_bound.min.y - sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.z < (plant_bound.min.z - sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.x > (plant_bound.max.x + sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.y > (plant_bound.max.y + sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.z > (plant_bound.max.z + sorghum_point_cloud_point_settings.bounding_box_limit))
      continue;
    auto ball_rand = glm::vec3(0.0f);
    if (sorghum_point_cloud_point_settings.ball_rand_radius > 0.0f) {
      ball_rand = glm::ballRand(sorghum_point_cloud_point_settings.ball_rand_radius);
    }
    const auto distance = glm::distance(sample.hit_info.position, sample.start);

    points.emplace_back(sample.hit_info.position +
                        distance * glm::vec3(glm::gaussRand(0.0f, sorghum_point_cloud_point_settings.variance),
                                             glm::gaussRand(0.0f, sorghum_point_cloud_point_settings.variance),
                                             glm::gaussRand(0.0f, sorghum_point_cloud_point_settings.variance)) +
                        ball_rand + (sample_index >= pc_samples.size() / 2 ? left_offset : right_offset));

    if (sorghum_point_cloud_point_settings.leaf_index) {
      switch (capture_settings->capture_mode) {
        case PointCloudCaptureSettings::CaptureMode::Cpu: {
          if (const auto search = leaf_mesh_renderer_handles.find(sample.handle);
              search != leaf_mesh_renderer_handles.end()) {
            leaf_indices.emplace_back(search->second.second);
          } else {
            leaf_indices.emplace_back(0);
          }
        } break;
        case PointCloudCaptureSettings::CaptureMode::Gpu: {
          leaf_indices.emplace_back(glm::floatBitsToUint(sample.hit_info.vertex_info1));
        } break;
      }
    }

    auto leaf_search = leaf_mesh_renderer_handles.find(sample.handle);
    auto stem_search = stem_mesh_renderer_handles.find(sample.handle);
    auto panicle_search = panicle_mesh_renderer_handles.find(sample.handle);
    if (sorghum_point_cloud_point_settings.instance_index) {
      if (leaf_search != leaf_mesh_renderer_handles.end()) {
        instance_indices.emplace_back(static_cast<int>(leaf_search->second.first));
      } else if (stem_search != stem_mesh_renderer_handles.end()) {
        instance_indices.emplace_back(static_cast<int>(stem_search->second));
      } else if (panicle_search != panicle_mesh_renderer_handles.end()) {
        instance_indices.emplace_back(static_cast<int>(panicle_search->second));
      } else {
        instance_indices.emplace_back(0);
      }
    }

    if (sorghum_point_cloud_point_settings.type_index) {
      // if (leaf_search != leaf_mesh_renderer_handles.end()) {
      //   type_indices.emplace_back(0);
      // } else if (stem_search != stem_mesh_renderer_handles.end()) {
      //   type_indices.emplace_back(1);
      // } else if (panicle_search != panicle_mesh_renderer_handles.end()) {
      //   type_indices.emplace_back(2);
      // } else if (sample.handle == ground_mesh_renderer_handle) {
      //   type_indices.emplace_back(3);
      // } else {
      //   type_indices.emplace_back(-1);
      // }

      if (leaf_search != leaf_mesh_renderer_handles.end()) {
        type_indices.emplace_back(2);
      } else if (stem_search != stem_mesh_renderer_handles.end()) {
        type_indices.emplace_back(1);
      } else if (panicle_search != panicle_mesh_renderer_handles.end()) {
        type_indices.emplace_back(3);
      } else if (sample.handle == ground_mesh_renderer_handle) {
        type_indices.emplace_back(0);
      } else {
        type_indices.emplace_back(-1);
      }
    }
  }
}

void SorghumPointCloudScanner::SavePointCloud(const std::filesystem::path& save_path,
                                              const std::vector<glm::vec3>& points,
                                              const std::vector<int>& leaf_indices,
                                              const std::vector<int>& instance_indices,
                                              const std::vector<int>& type_indices) const {
  std::filebuf fb_binary;
  fb_binary.open(save_path.string(), std::ios::out | std::ios::binary);
  std::ostream ostream(&fb_binary);
  if (ostream.fail())
    throw std::runtime_error("failed to open " + save_path.string());

  tinyply::PlyFile cube_file;
  cube_file.add_properties_to_element("vertex", {"x", "y", "z"}, tinyply::Type::FLOAT32, points.size(),
                                      static_cast<const uint8_t*>(static_cast<const void*>(points.data())),
                                      tinyply::Type::INVALID, 0);

  if (sorghum_point_cloud_point_settings.type_index)
    cube_file.add_properties_to_element("type_index", {"type_index"}, tinyply::Type::INT32, type_indices.size(),
                                        static_cast<const uint8_t*>(static_cast<const void*>(type_indices.data())),
                                        tinyply::Type::INVALID, 0);

  if (sorghum_point_cloud_point_settings.instance_index) {
    cube_file.add_properties_to_element(
        "instance_index", {"instance_index"}, tinyply::Type::INT32, instance_indices.size(),
        static_cast<const uint8_t*>(static_cast<const void*>(instance_indices.data())), tinyply::Type::INVALID, 0);
  }

  if (sorghum_point_cloud_point_settings.leaf_index) {
    cube_file.add_properties_to_element("leaf_index", {"leaf_index"}, tinyply::Type::INT32, leaf_indices.size(),
                                        static_cast<const uint8_t*>(static_cast<const void*>(leaf_indices.data())),
                                        tinyply::Type::INVALID, 0);
  }
  // Write a binary file
  cube_file.write(ostream, true);
}

void SorghumPointCloudScanner::WriteSplineInfo(const std::filesystem::path& save_path,
                                               const std::shared_ptr<PointCloudCaptureSettings>& capture_settings) {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const std::vector<Entity>* sorghum_entities = scene->UnsafeGetPrivateComponentOwnersList<Sorghum>();
  if (sorghum_entities == nullptr) {
    EVOENGINE_ERROR("No sorghums!");
    return;
  }
  try {
    std::filesystem::path yaml_path = save_path;
    yaml_path.replace_extension(".yml");
    YAML::Emitter out;
    out << YAML::BeginMap;
    out << YAML::Key << "Sorghums" << YAML::BeginSeq;
    for (const auto& sorghum_entity : *sorghum_entities) {
      if (scene->IsEntityValid(sorghum_entity)) {
        if (capture_settings->output_spline_info) {
          const auto sorghum = scene->GetOrSetPrivateComponent<Sorghum>(sorghum_entity).lock();
          const auto sorghum_descriptor = sorghum->sorghum_descriptor.Get<SorghumDescriptor>();
          out << YAML::BeginMap;
          {
            out << YAML::Key << "Instance Index" << YAML::Value << sorghum_entity.GetIndex();
            out << YAML::Key << "Leaves" << YAML::BeginSeq;
            for (const auto& leaf : sorghum_descriptor->leaves) {
              out << YAML::BeginMap;
              std::vector<glm::vec3> points(capture_settings->spline_subdivision_count);

              std::vector<glm::vec3> left_points(capture_settings->spline_subdivision_count);
              std::vector<glm::vec3> right_points(capture_settings->spline_subdivision_count);

              SorghumSpline leaf_part;
              leaf_part.segments = leaf.spline.GetLeafPart();
              const auto segments = leaf_part.RebuildFixedSizeSegments(capture_settings->spline_subdivision_count);
              for (uint32_t node_index = 0; node_index < capture_settings->spline_subdivision_count; node_index++) {
                const auto& segment = segments[node_index];
                points[node_index] = segment.position;
                left_points[node_index] = segment.GetLeafPoint(-segment.theta);
                right_points[node_index] = segment.GetLeafPoint(segment.theta);
              }
              out << YAML::Key << "Leaf Index" << YAML::Value << leaf.index + 1;
              Serialization::SerializeVector("Center Points", points, out);
              Serialization::SerializeVector("Left Points", left_points, out);
              Serialization::SerializeVector("Right Points", right_points, out);
              out << YAML::EndMap;
            }
            out << YAML::EndSeq;
          }
          out << YAML::EndMap;
        }
      }
    }
    out << YAML::EndSeq;
    out << YAML::EndMap;
    std::ofstream output_file(yaml_path.string());
    output_file << out.c_str();
    output_file.flush();
  } catch (const std::exception& e) {
    EVOENGINE_ERROR("Failed to save!");
  }
}

void SorghumPointCloudScanner::Capture(const std::filesystem::path& save_path,
                                       const std::shared_ptr<PointCloudCaptureSettings>& capture_settings) const {
  const auto scene = ApplicationContext::Get().GetActiveScene();
  const std::vector<Entity>* sorghum_entities = scene->UnsafeGetPrivateComponentOwnersList<Sorghum>();
  if (sorghum_entities == nullptr) {
    EVOENGINE_ERROR("No sorghums!");
    return;
  }
  std::vector<glm::vec3> points;
  std::vector<int> leaf_indices;
  std::vector<int> instance_indices;
  std::vector<int> type_indices;

  Scan(capture_settings, points, leaf_indices, instance_indices, type_indices);
  SavePointCloud(save_path, points, leaf_indices, instance_indices, type_indices);

  if (capture_settings->output_spline_info) {
    WriteSplineInfo(save_path, capture_settings);
  }
}

SorghumFractionalCoverResult SorghumPointCloudScanner::CalculateFractionalCover(
    const SorghumFractionalCoverSettings& settings) const {
  SorghumFractionalCoverResult result;
  const auto scene = GetScene();
  if (!scene) {
    EVOENGINE_ERROR("Sorghum fractional cover failed: no active scene!")
    return result;
  }
  const auto sorghum_entities = scene->UnsafeGetPrivateComponentOwnersList<Sorghum>();
  if (!sorghum_entities || sorghum_entities->empty()) {
    EVOENGINE_ERROR("Sorghum fractional cover failed: no sorghums!")
    return result;
  }

  std::unordered_set<Handle> plant_renderer_handles;
  for (const auto& sorghum_entity : *sorghum_entities) {
    if (!scene->IsEntityValid(sorghum_entity))
      continue;
    std::vector<Entity> stack = scene->GetChildren(sorghum_entity);
    while (!stack.empty()) {
      const auto entity = stack.back();
      stack.pop_back();
      if (!scene->IsEntityValid(entity))
        continue;
      if (scene->HasPrivateComponent<MeshRenderer>(entity))
        plant_renderer_handles.emplace(scene->GetOrSetPrivateComponent<MeshRenderer>(entity).lock()->GetHandle());
      if (scene->HasPrivateComponent<Particles>(entity))
        plant_renderer_handles.emplace(scene->GetOrSetPrivateComponent<Particles>(entity).lock()->GetHandle());
      if (scene->HasPrivateComponent<StrandsRenderer>(entity))
        plant_renderer_handles.emplace(scene->GetOrSetPrivateComponent<StrandsRenderer>(entity).lock()->GetHandle());
      const auto& children = scene->GetChildren(entity);
      stack.insert(stack.end(), children.begin(), children.end());
    }
  }

  Handle ground_renderer_handle = 0;
  if (const auto soil_candidate = EcoSysLabLayer::FindSoil(); !soil_candidate.expired()) {
    const auto soil = soil_candidate.lock();
    const auto soil_entity = soil->GetOwner();
    if (scene->IsEntityValid(soil_entity)) {
      scene->ForEachChild(soil_entity, [&](const Entity child) {
        if (scene->GetEntityName(child) == "Ground Mesh" && scene->HasPrivateComponent<MeshRenderer>(child))
          ground_renderer_handle = scene->GetOrSetPrivateComponent<MeshRenderer>(child).lock()->GetHandle();
      });
    }
  }

  std::vector<PointCloudSample> samples;
  settings.GenerateSamples(samples);
  if (samples.empty()) {
    EVOENGINE_ERROR("Sorghum fractional cover failed: invalid sampling settings!")
    return result;
  }

#ifdef CUDA_MODULE_SERVICE
  const auto ray_tracer_layer = ApplicationContext::Get().GetLayer<RayTracerLayer>();
  if (!ray_tracer_layer) {
    EVOENGINE_ERROR("Sorghum fractional cover failed: missing RayTracerLayer!")
    return result;
  }
  CudaModule::SamplePointCloud(ray_tracer_layer->environment_properties, samples);
#else
  EVOENGINE_ERROR("Sorghum fractional cover failed: missing CudaModule Service!")
  return result;
#endif

  result.resolution = settings.resolution;
  result.cover.resize(static_cast<size_t>(settings.resolution.x) * settings.resolution.y);
  const size_t samples_per_pixel =
      static_cast<size_t>(settings.samples_per_pixel_axis) * settings.samples_per_pixel_axis;
  for (size_t pixel_index = 0; pixel_index < result.cover.size(); ++pixel_index) {
    uint32_t pixel_plant_hits = 0;
    for (size_t local_sample_index = 0; local_sample_index < samples_per_pixel; ++local_sample_index) {
      const auto& sample = samples[pixel_index * samples_per_pixel + local_sample_index];
      if (sample.hit_count == 0) {
        ++result.miss_count;
      } else if (plant_renderer_handles.find(sample.handle) != plant_renderer_handles.end()) {
        ++pixel_plant_hits;
        ++result.plant_hits;
      } else if (sample.handle == ground_renderer_handle) {
        ++result.ground_hits;
      } else {
        ++result.unknown_hits;
      }
    }
    result.cover[pixel_index] = static_cast<float>(pixel_plant_hits) / static_cast<float>(samples_per_pixel);
  }
  result.total_cover = static_cast<float>(result.plant_hits) / static_cast<float>(samples.size());
  return result;
}

void SorghumPointCloudScanner::SaveFractionalCover(const std::filesystem::path& save_path,
                                                   const SorghumFractionalCoverSettings& settings,
                                                   const SorghumFractionalCoverResult& result) {
  if (result.cover.empty())
    return;
  std::ofstream csv(save_path);
  if (!csv)
    throw std::runtime_error("failed to open " + save_path.string());
  csv << std::setprecision(9);
  for (int y = 0; y < result.resolution.y; ++y) {
    for (int x = 0; x < result.resolution.x; ++x) {
      if (x != 0)
        csv << ',';
      csv << result.cover[static_cast<size_t>(y) * result.resolution.x + x];
    }
    csv << '\n';
  }

  auto metadata_path = save_path;
  metadata_path.replace_extension(".yml");
  YAML::Emitter out;
  out << YAML::BeginMap;
  out << YAML::Key << "method" << YAML::Value << "geometric_ray_hit_ratio";
  out << YAML::Key << "denominator" << YAML::Value << "all_rays_in_scan_area";
  out << YAML::Key << "plant_classes" << YAML::Value << "leaf,stem,panicle";
  out << YAML::Key << "center" << YAML::Value << settings.center;
  out << YAML::Key << "area_size" << YAML::Value << settings.area_size;
  out << YAML::Key << "resolution" << YAML::Value << result.resolution;
  out << YAML::Key << "samples_per_pixel_axis" << YAML::Value << settings.samples_per_pixel_axis;
  out << YAML::Key << "scan_height" << YAML::Value << settings.scan_height;
  out << YAML::Key << "total_cover" << YAML::Value << result.total_cover;
  out << YAML::Key << "plant_hits" << YAML::Value << result.plant_hits;
  out << YAML::Key << "ground_hits" << YAML::Value << result.ground_hits;
  out << YAML::Key << "miss_count" << YAML::Value << result.miss_count;
  out << YAML::Key << "unknown_hits" << YAML::Value << result.unknown_hits;
  out << YAML::EndMap;
  std::ofstream metadata(metadata_path);
  if (!metadata)
    throw std::runtime_error("failed to open " + metadata_path.string());
  metadata << out.c_str();
}

void SorghumPointCloudScanner::CaptureFractionalCover(const std::filesystem::path& save_path) const {
  const auto result = CalculateFractionalCover(fractional_cover_settings);
  SaveFractionalCover(save_path, fractional_cover_settings, result);
  if (!result.cover.empty()) {
    EVOENGINE_LOG("Sorghum fractional cover: " + std::to_string(result.total_cover) +
                  ", plant=" + std::to_string(result.plant_hits) + ", ground=" + std::to_string(result.ground_hits) +
                  ", miss=" + std::to_string(result.miss_count) + ", unknown=" + std::to_string(result.unknown_hits));
  }
}

bool dataset_generation_package::InspectSorghumPointCloudScanner(InspectorContext& context,
                                                                 SorghumPointCloudScanner& scanner) {
  (void)context;
  bool changed = false;
  if (ImGui::TreeNodeEx("Grid Capture")) {
    static std::shared_ptr<TreePointCloudGridCaptureSettings> capture_settings =
        std::make_shared<TreePointCloudGridCaptureSettings>();
    capture_settings->DrawGui();
    FileUtils::SaveFile(
        "Capture", "Point Cloud", {".ply"},
        [&](const std::filesystem::path& path) {
          scanner.Capture(path, capture_settings);
        },
        false);
    ImGui::TreePop();
  }
  if (ImGui::TreeNodeEx("Fractional Cover")) {
    changed |= scanner.fractional_cover_settings.DrawGui();
    const auto& settings = scanner.fractional_cover_settings;
    const auto ray_count = static_cast<unsigned long long>(settings.resolution.x) * settings.resolution.y *
                           settings.samples_per_pixel_axis * settings.samples_per_pixel_axis;
    ImGui::Text("Ray count: %llu", ray_count);
    FileUtils::SaveFile(
        "Capture FC", "Fractional Cover", {".csv"},
        [&](const std::filesystem::path& path) {
          scanner.CaptureFractionalCover(path);
        },
        false);
    ImGui::TreePop();
  }
  if (ImGui::TreeNodeEx("Point settings")) {
    if (scanner.sorghum_point_cloud_point_settings.DrawGui())
      changed = true;
    ImGui::TreePop();
  }
  return changed;
}

void SorghumPointCloudScanner::OnDestroy() {
  sorghum_point_cloud_point_settings = {};
  fractional_cover_settings = {};
}

void dataset_generation_package::SerializeSorghumPointCloudScanner(YAML::Emitter& out,
                                                                   const SorghumPointCloudScanner& target) {
  target.sorghum_point_cloud_point_settings.Save("sorghum_point_cloud_point_settings", out);
  target.fractional_cover_settings.Save("fractional_cover_settings", out);
}

void dataset_generation_package::DeserializeSorghumPointCloudScanner(const YAML::Node& in,
                                                                     SorghumPointCloudScanner& target) {
  target.sorghum_point_cloud_point_settings.Load("sorghum_point_cloud_point_settings", in);
  target.fractional_cover_settings.Load("fractional_cover_settings", in);
}

void GantryPointCloudScanner::Scan(const std::vector<Entity>& targets, const std::vector<std::vector<int>>& label_lists,
                                   const std::shared_ptr<PointCloudCaptureSettings>& capture_settings,
                                   std::vector<glm::vec3>& points, std::vector<int>& leaf_indices,
                                   std::vector<int>& instance_indices, std::vector<int>& type_indices) const {
  const auto render_layer = ApplicationContext::Get().GetLayer<RenderLayer>();
  const auto scene = GetScene();
  if (!scene) {
    EVOENGINE_ERROR("No active scene!")
    return;
  }
  if (targets.size() != label_lists.size()) {
    EVOENGINE_ERROR("GantryPointCloudScanner::Scan failed: targets and label_lists size mismatch!")
    return;
  }

  Bound plant_bound{};
  std::unordered_map<Handle, int> mesh_renderer_instance_indices;
  std::unordered_map<Handle, const std::vector<int>*> mesh_renderer_label_lists;

  for (size_t target_index = 0; target_index < targets.size(); target_index++) {
    const auto target = targets[target_index];
    if (!scene->IsEntityValid(target))
      continue;

    std::vector<Entity> stack{target};
    while (!stack.empty()) {
      const auto current = stack.back();
      stack.pop_back();

      if (scene->HasPrivateComponent<MeshRenderer>(current)) {
        const auto mesh_renderer = scene->GetOrSetPrivateComponent<MeshRenderer>(current).lock();
        const auto mesh = mesh_renderer->mesh.Get<Mesh>();
        if (mesh) {
          mesh_renderer_instance_indices[mesh_renderer->GetHandle()] = static_cast<int>(target_index);

          const auto global_transform = scene->GetDataComponent<GlobalTransform>(current);
          plant_bound.min =
              glm::min(plant_bound.min, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().min, 1.0f)));
          plant_bound.max =
              glm::max(plant_bound.max, glm::vec3(global_transform.value * glm::vec4(mesh->GetBound().max, 1.0f)));
        }
      }

      for (const auto& child : scene->GetChildren(current)) {
        if (scene->IsEntityValid(child)) {
          stack.emplace_back(child);
        }
      }
    }
  }

  std::vector<PointCloudSample> pc_samples;
  capture_settings->GenerateSamples(pc_samples);

  switch (capture_settings->capture_mode) {
    case PointCloudCaptureSettings::CaptureMode::OptiX: {
#ifdef CUDA_MODULE_SERVICE
      CudaModule::SamplePointCloud(ApplicationContext::Get().GetLayer<RayTracerLayer>()->environment_properties,
                                   pc_samples);
#else
      EVOENGINE_ERROR("Missing CudaModule Service!")
#endif
    } break;
    case PointCloudCaptureSettings::CaptureMode::Cpu: {
      std::shared_ptr<RenderInstanceStorage> render_instances{};
      if (render_layer) {
        render_instances = render_layer->GetCurrentRenderInstanceStorage();
      }
      if (!render_instances) {
        render_instances = std::make_shared<RenderInstanceStorage>();
        Bound world_bound;
        render_instances->BuildFromScene({}, ApplicationContext::Get().GetActiveScene(), world_bound);
      }
      CpuRayTracer cpu_ray_tracer;
      cpu_ray_tracer.Initialize(
          render_instances,
          [&](uint32_t, const std::shared_ptr<Mesh>&) {
          },
          [&](const uint32_t, const Entity&) {
          });
      cpu_ray_tracer.SamplePointCloud(pc_samples);
    } break;
    case PointCloudCaptureSettings::CaptureMode::Gpu: {
      std::shared_ptr<RenderInstanceStorage> render_instances{};
      if (render_layer) {
        render_instances = render_layer->GetCurrentRenderInstanceStorage();
      }
      if (!render_instances) {
        render_instances = std::make_shared<RenderInstanceStorage>();
        Bound world_bound;
        render_instances->BuildFromScene({}, ApplicationContext::Get().GetActiveScene(), world_bound);
      }
      CpuRayTracer cpu_ray_tracer;
      cpu_ray_tracer.Initialize(
          render_instances,
          [&](uint32_t, const std::shared_ptr<Mesh>&) {
          },
          [&](const uint32_t, const Entity&) {
          });
      auto aggregate_scene = cpu_ray_tracer.Aggregate();
      aggregate_scene.InitializeBuffers();
      aggregate_scene.SamplePointCloudGpu(cpu_ray_tracer, pc_samples);
    } break;
  }

  const glm::vec3 left_offset = glm::linearRand(-left_random_offset, left_random_offset);
  const glm::vec3 right_offset = glm::linearRand(-right_random_offset, right_random_offset);
  for (int sample_index = 0; sample_index < pc_samples.size(); sample_index++) {
    const auto& sample = pc_samples.at(sample_index);
    if (sample.hit_count == 0)
      continue;
    if (!capture_settings->SampleFilter(sample))
      continue;
    if (const auto search = mesh_renderer_instance_indices.find(sample.handle);
        search == mesh_renderer_instance_indices.end()) {
      continue;
    }

    auto& position = sample.hit_info.position;
    if (position.x < (plant_bound.min.x - sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.y < (plant_bound.min.y - sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.z < (plant_bound.min.z - sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.x > (plant_bound.max.x + sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.y > (plant_bound.max.y + sorghum_point_cloud_point_settings.bounding_box_limit) ||
        position.z > (plant_bound.max.z + sorghum_point_cloud_point_settings.bounding_box_limit))
      continue;

    auto ball_rand = glm::vec3(0.0f);
    if (sorghum_point_cloud_point_settings.ball_rand_radius > 0.0f) {
      ball_rand = glm::ballRand(sorghum_point_cloud_point_settings.ball_rand_radius);
    }
    const auto distance = glm::distance(sample.hit_info.position, sample.start);

    points.emplace_back(sample.hit_info.position +
                        distance * glm::vec3(glm::gaussRand(0.0f, sorghum_point_cloud_point_settings.variance),
                                             glm::gaussRand(0.0f, sorghum_point_cloud_point_settings.variance),
                                             glm::gaussRand(0.0f, sorghum_point_cloud_point_settings.variance)) +
                        ball_rand + (sample_index >= pc_samples.size() / 2 ? left_offset : right_offset));

    if (sorghum_point_cloud_point_settings.leaf_index) {
      int leaf_label = -1;
      if (const auto label_search = mesh_renderer_instance_indices.find(sample.handle);
          label_search != mesh_renderer_instance_indices.end()) {
        const auto& instance = label_search->second;
        if (instance >= 0 && instance < label_lists.size() &&
            sample.hit_info.triangle_index < label_lists[instance].size()) {
          leaf_label = label_lists[instance][sample.hit_info.triangle_index];
        }
      }
      leaf_indices.emplace_back(leaf_label);
    }
    if (sorghum_point_cloud_point_settings.instance_index) {
      instance_indices.emplace_back(mesh_renderer_instance_indices.at(sample.handle));
    }
    if (sorghum_point_cloud_point_settings.type_index) {
      type_indices.emplace_back(0);
    }
  }
}

void GantryPointCloudScanner::SavePointCloud(const std::filesystem::path& save_path,
                                             const std::vector<glm::vec3>& points, const std::vector<int>& leaf_indices,
                                             const std::vector<int>& instance_indices,
                                             const std::vector<int>& type_indices) const {
  std::filebuf fb_binary;
  fb_binary.open(save_path.string(), std::ios::out | std::ios::binary);
  std::ostream ostream(&fb_binary);
  if (ostream.fail())
    throw std::runtime_error("failed to open " + save_path.string());

  tinyply::PlyFile cube_file;
  cube_file.add_properties_to_element("vertex", {"x", "y", "z"}, tinyply::Type::FLOAT32, points.size(),
                                      static_cast<const uint8_t*>(static_cast<const void*>(points.data())),
                                      tinyply::Type::INVALID, 0);

  if (sorghum_point_cloud_point_settings.type_index) {
    cube_file.add_properties_to_element("type_index", {"type_index"}, tinyply::Type::INT32, type_indices.size(),
                                        static_cast<const uint8_t*>(static_cast<const void*>(type_indices.data())),
                                        tinyply::Type::INVALID, 0);
  }
  if (sorghum_point_cloud_point_settings.instance_index) {
    cube_file.add_properties_to_element(
        "instance_index", {"instance_index"}, tinyply::Type::INT32, instance_indices.size(),
        static_cast<const uint8_t*>(static_cast<const void*>(instance_indices.data())), tinyply::Type::INVALID, 0);
  }
  if (sorghum_point_cloud_point_settings.leaf_index) {
    cube_file.add_properties_to_element("leaf_index", {"leaf_index"}, tinyply::Type::INT32, leaf_indices.size(),
                                        static_cast<const uint8_t*>(static_cast<const void*>(leaf_indices.data())),
                                        tinyply::Type::INVALID, 0);
  }
  cube_file.write(ostream, true);
}

bool GantryPointCloudScanner::DrawGui(const std::shared_ptr<EditorLayer>& editor_layer) {
  return false;
}

void GantryPointCloudScanner::OnDestroy() {
  IPrivateComponent::OnDestroy();
}

void GantryPointCloudScanner::Serialize(YAML::Emitter& out) const {
  sorghum_point_cloud_point_settings.Save("sorghum_point_cloud_point_settings", out);
}

void GantryPointCloudScanner::Deserialize(const YAML::Node& in) {
  sorghum_point_cloud_point_settings.Load("sorghum_point_cloud_point_settings", in);
}

void GantryPointCloudScanner::CaptureLabeledMeshes(
    const std::vector<Entity>& targets, const std::vector<std::vector<int>>& label_lists,
    const std::filesystem::path& save_path, const std::shared_ptr<PointCloudCaptureSettings>& capture_settings) const {
  std::vector<glm::vec3> points;
  std::vector<int> leaf_indices;
  std::vector<int> instance_indices;
  std::vector<int> type_indices;
  Scan(targets, label_lists, capture_settings, points, leaf_indices, instance_indices, type_indices);
  SavePointCloud(save_path, points, leaf_indices, instance_indices, type_indices);
}
