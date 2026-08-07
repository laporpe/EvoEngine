#pragma once

#include "PointCloudScannerUtils.hpp"

namespace dataset_generation_package {
using namespace evo_engine;
struct SorghumPointCloudPointSettings {
  float variance = 0.015f;
  float ball_rand_radius = 0.01f;

  bool type_index = true;
  bool instance_index = true;
  bool leaf_index = true;

  float bounding_box_limit = 2.f;

  bool DrawGui();
  void Save(const std::string& name, YAML::Emitter& out) const;
  void Load(const std::string& name, const YAML::Node& in);
};

class SorghumPointCloudGridCaptureSettings : public PointCloudCaptureSettings {
 public:
  float bounding_box_size = 3.;

  glm::ivec2 grid_size = {5, 5};
  float grid_distance = 1.25f;
  float step = 0.01f;
  int drone_sample = 512;
  float drone_height = 2.5f;
  bool DrawGui() override;
  void GenerateSamples(std::vector<PointCloudSample>& point_cloud_samples) override;
  bool SampleFilter(const PointCloudSample& sample) override;
};

class SorghumGantryCaptureSettings : public PointCloudCaptureSettings {
 public:
  float bounding_box_size = 10.;

  glm::ivec2 grid_size = {1, 1};
  glm::vec2 grid_distance = {2, 2};
  float step = 0.0075f;
  float sample_height = 2.5f;

  std::vector<float> scanner_angles = {30.f};

  bool DrawGui() override;
  void GenerateSamples(std::vector<PointCloudSample>& point_cloud_samples) override;
  bool SampleFilter(const PointCloudSample& sample) override;
};

struct SorghumFractionalCoverSettings {
  glm::vec2 center = glm::vec2(0.f);
  glm::vec2 area_size = glm::vec2(5.f);
  glm::ivec2 resolution = glm::ivec2(256);
  int samples_per_pixel_axis = 4;
  float scan_height = 5.f;

  bool DrawGui();
  void Save(const std::string& name, YAML::Emitter& out) const;
  void Load(const std::string& name, const YAML::Node& in);
  void GenerateSamples(std::vector<PointCloudSample>& samples) const;
};

struct SorghumFractionalCoverResult {
  glm::ivec2 resolution = glm::ivec2(0);
  std::vector<float> cover;
  float total_cover = 0.f;
  uint64_t plant_hits = 0;
  uint64_t ground_hits = 0;
  uint64_t miss_count = 0;
  uint64_t unknown_hits = 0;
};

class SorghumPointCloudScanner : public IPrivateComponent {
 public:
  glm::vec3 left_random_offset = glm::vec3(0.0f);
  glm::vec3 right_random_offset = glm::vec3(0.0f);
  SorghumPointCloudPointSettings sorghum_point_cloud_point_settings{};
  SorghumFractionalCoverSettings fractional_cover_settings{};

  void Scan(const std::shared_ptr<PointCloudCaptureSettings>& capture_settings, std::vector<glm::vec3>& points,
            std::vector<int>& leaf_indices, std::vector<int>& instance_indices, std::vector<int>& type_indices) const;

  void SavePointCloud(const std::filesystem::path& save_path, const std::vector<glm::vec3>& points,
                      const std::vector<int>& leaf_indices, const std::vector<int>& instance_indices,
                      const std::vector<int>& type_indices) const;

  static void WriteSplineInfo(const std::filesystem::path& save_path,
                              const std::shared_ptr<PointCloudCaptureSettings>& capture_settings);
  void Capture(const std::filesystem::path& save_path,
               const std::shared_ptr<PointCloudCaptureSettings>& capture_settings) const;

  [[nodiscard]] SorghumFractionalCoverResult CalculateFractionalCover(
      const SorghumFractionalCoverSettings& settings) const;
  static void SaveFractionalCover(const std::filesystem::path& save_path,
                                  const SorghumFractionalCoverSettings& settings,
                                  const SorghumFractionalCoverResult& result);
  void CaptureFractionalCover(const std::filesystem::path& save_path) const;

  void OnDestroy() override;
};

class GantryPointCloudScanner : public IPrivateComponent {
 public:
  glm::vec3 left_random_offset = glm::vec3(0.0f);
  glm::vec3 right_random_offset = glm::vec3(0.0f);
  SorghumPointCloudPointSettings sorghum_point_cloud_point_settings{};

  void Scan(const std::vector<Entity>& targets, const std::vector<std::vector<int>>& label_lists,
            const std::shared_ptr<PointCloudCaptureSettings>& capture_settings, std::vector<glm::vec3>& points,
            std::vector<int>& leaf_indices, std::vector<int>& instance_indices, std::vector<int>& type_indices) const;

  void SavePointCloud(const std::filesystem::path& save_path, const std::vector<glm::vec3>& points,
                      const std::vector<int>& leaf_indices, const std::vector<int>& instance_indices,
                      const std::vector<int>& type_indices) const;

  bool DrawGui(const std::shared_ptr<EditorLayer>& editor_layer);

  void OnDestroy() override;

  void Serialize(YAML::Emitter& out) const;
  void Deserialize(const YAML::Node& in);

  void CaptureLabeledMeshes(const std::vector<Entity>& targets, const std::vector<std::vector<int>>& label_lists,
                            const std::filesystem::path& save_path,
                            const std::shared_ptr<PointCloudCaptureSettings>& capture_settings) const;
};
}  // namespace dataset_generation_package
