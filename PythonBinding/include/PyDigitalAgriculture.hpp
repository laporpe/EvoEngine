#pragma once

#ifdef DIGITAL_AGRICULTURE_PACKAGE

// #  include "AnimationPlayer.hpp"
// #  include "Application.hpp"
// #  include "ClassRegistry.hpp"
// #  include "Climate.hpp"
// #  include "EditorLayer.hpp"
// #  include "HeightField.hpp"
// #  include "MeshRenderer.hpp"
#  include <array>
#  include <map>
#  include "EditorLayer.hpp"
#  include "IPrivateComponent.hpp"
#  include "ObjectRotator.hpp"
#  include "PlayerController.hpp"
#  include "PostProcessingStack.hpp"
#  include "Prefab.hpp"
#  include "ProjectManager.hpp"
#  include "RadialBoundingVolume.hpp"
#  include "RenderLayer.hpp"
#  include "Scene.hpp"
#  include "ShootModel.hpp"
#  include "Soil.hpp"
#  include "SorghumLayer.hpp"
#  include "Times.hpp"
#  include "Tree.hpp"
#  include "TreeStructor.hpp"
#  include "WindowLayer.hpp"
#  include "pybind11/pybind11.h"
#  include "pybind11/stl.h"
#  include "pybind11/stl/filesystem.h"

#  if DATASET_GENERATION_PACKAGE
#    include <SorghumPointCloudScanner.hpp>
#    include "DatasetGenerator.hpp"
#  endif
#  include "PyEvoEngine.hpp"

namespace py_digital_agriculture_package {
#  if DATASET_GENERATION_PACKAGE
using namespace dataset_generation_package;
#  endif

using namespace evo_engine;
using namespace py_evo_engine;
using namespace digital_agriculture_package;

struct ParbarProbeRecord {
  std::string cultivar;
  std::string model;
  std::string sensor_bar_level;
  std::string height_rule;
  uint32_t row = 0;
  uint32_t column = 0;
  uint32_t represented_plant_count = 0;
  glm::vec3 position = glm::vec3(0.0f);
  glm::vec3 normal = glm::vec3(0.0f, 1.0f, 0.0f);
  glm::vec3 energy = glm::vec3(0.0f);
  glm::vec3 direction = glm::vec3(0.0f);
  float average_represented_root_elevation_m = 0.0f;
  float average_represented_plant_height_m = 0.0f;
  float sensor_top_elevation_m = 0.0f;
  float height_fraction_of_average_height = 0.0f;
  float scalar = 0.0f;
  float normalized = 0.0f;
};

struct LSystemGridIlluminationRecord {
  std::string name;
  std::string cultivar;
  uint32_t row = 0;
  uint32_t column = 0;
  glm::vec3 position = glm::vec3(0.0f);
  uint32_t triangle_count = 0;
  uint32_t leaf_triangle_count = 0;
  uint32_t stem_triangle_count = 0;
  float area = 0.0f;
  float leaf_area = 0.0f;
  float stem_area = 0.0f;
  float plant_height_m = 0.0f;
  glm::vec3 total_flux = glm::vec3(0.0f);
  glm::vec3 average_flux = glm::vec3(0.0f);
  float scalar = 0.0f;
  glm::vec3 isolated_total_flux = glm::vec3(0.0f);
  glm::vec3 isolated_average_flux = glm::vec3(0.0f);
  float isolated_scalar = 0.0f;
  float retention_ratio = 1.0f;
  float shadow_loss = 0.0f;
  float normalized = 0.0f;
};

struct LSystemAxisPhenotypeRecord {
  int axis_id = 0;
  int origin_rank = 0;
  uint32_t leaf_count = 0;
  uint32_t expanded_leaf_count = 0;
  uint32_t internode_count = 0;
  float origin_height_m = 0.0f;
  float culm_tip_height_m = 0.0f;
  float culm_departure_degrees = 0.0f;
  float highest_mature_collar_height_m = 0.0f;
  float leaf_ratio_to_main = 1.0f;
  float height_ratio_to_main = 1.0f;
};

struct LSystemLeafPhenotypeRecord {
  int axis_id = 0;
  int origin_rank = 0;
  int rank = 0;
  int axis_phytomer_count = 0;
  float normalized_rank = 0.0f;
  float age_gdd = 0.0f;
  float growth_progress = 0.0f;
  float blade_length_m = 0.0f;
  float target_blade_length_m = 0.0f;
  float blade_width_m = 0.0f;
  float target_blade_width_m = 0.0f;
  float insertion_angle_degrees = 0.0f;
  float target_insertion_angle_degrees = 0.0f;
  float collar_height_m = 0.0f;
  float tip_height_m = 0.0f;
  float maximum_height_m = 0.0f;
  float chord_elevation_degrees = 0.0f;
  float distal_elevation_degrees = 0.0f;
  float gravity_tip_deflection_m = 0.0f;
  float centerline_lateral_span_m = 0.0f;
  float centerline_arc_to_chord_ratio = 1.0f;
  float surface_waviness_rms_m = 0.0f;
  bool alive = false;
  bool is_flag_leaf = false;
};

struct LSystemInternodePhenotypeRecord {
  int axis_id = 0;
  int origin_rank = 0;
  int rank = 0;
  int axis_phytomer_count = 0;
  float normalized_rank = 0.0f;
  float age_gdd = 0.0f;
  float growth_progress = 0.0f;
  float length_m = 0.0f;
  float target_length_m = 0.0f;
  float diameter_m = 0.0f;
  float target_diameter_m = 0.0f;
  float base_height_m = 0.0f;
  float tip_height_m = 0.0f;
};

struct LSystemDescriptorPhenotypeRecord {
  uint32_t seed = 0;
  uint32_t leaf_count = 0;
  uint32_t live_leaf_count = 0;
  uint32_t main_culm_leaf_count = 0;
  uint32_t main_culm_expanded_leaf_count = 0;
  uint32_t tiller_leaf_count = 0;
  uint32_t tiller_expanded_leaf_count = 0;
  uint32_t primary_tiller_count = 0;
  uint32_t triangle_count = 0;
  uint32_t leaf_triangle_count = 0;
  uint32_t stem_triangle_count = 0;
  uint32_t panicle_branch_count = 0;
  uint32_t panicle_spikelet_count = 0;
  float height_m = 0.0f;
  float panicle_tip_height_m = 0.0f;
  float main_culm_tip_height_m = 0.0f;
  float main_culm_highest_mature_collar_height_m = 0.0f;
  float main_culm_tip_height_ratio = 0.0f;
  float main_culm_mature_collar_height_ratio = 0.0f;
  float main_culm_max_blade_length_m = 0.0f;
  float main_culm_max_target_blade_length_m = 0.0f;
  float main_culm_max_blade_width_m = 0.0f;
  float main_culm_max_target_blade_width_m = 0.0f;
  float area = 0.0f;
  float leaf_area = 0.0f;
  float stem_area = 0.0f;
  bool has_geometry = false;
  bool panicle_emerged = false;
  std::vector<LSystemAxisPhenotypeRecord> axes;
  std::vector<LSystemLeafPhenotypeRecord> leaves;
  std::vector<LSystemInternodePhenotypeRecord> internodes;
};

struct LSystemPlantSceneMetadataRecord {
  std::string name;
  std::string cultivar;
  std::string descriptor_asset_path;
  uint32_t descriptor_version = 0;
  uint32_t seed = 0;
  float evaluation_gdd = 0.0f;
  glm::vec3 local_position = glm::vec3(0.0f);
  glm::vec3 global_position = glm::vec3(0.0f);
  glm::vec3 geometry_min_position = glm::vec3(0.0f);
  glm::vec3 geometry_max_position = glm::vec3(0.0f);
  uint32_t leaf_count = 0;
  uint32_t main_culm_leaf_count = 0;
  uint32_t tiller_leaf_count = 0;
  uint32_t primary_tiller_count = 0;
  uint32_t geometry_snapshot_schema_version = 0;
  uint64_t geometry_snapshot_version = 0;
  uint32_t geometry_snapshot_organ_count = 0;
  uint32_t leaf_vertex_count = 0;
  uint32_t leaf_triangle_count = 0;
  uint32_t culm_vertex_count = 0;
  uint32_t culm_triangle_count = 0;
  uint32_t panicle_vertex_count = 0;
  uint32_t panicle_triangle_count = 0;
  uint32_t panicle_branch_count = 0;
  uint32_t panicle_spikelet_count = 0;
  uint32_t vegetative_organ_count = 0;
  uint32_t immature_vegetative_organ_count = 0;
  uint32_t panicle_organ_count = 0;
  uint32_t immature_panicle_organ_count = 0;
  uint32_t developmental_module_count = 0;
  double last_grow_seconds = 0.0;
  double last_rebuild_seconds = 0.0;
  double last_rebuild_internode_seconds = 0.0;
  double last_leaf_spline_seconds = 0.0;
  double last_leaf_mesh_seconds = 0.0;
  double last_mesh_upload_seconds = 0.0;
  float leaf_width_scale = 1.0f;
  float leaf_thickness_m = 0.001f;
  float plant_height_m = 0.0f;
  float leaf_area_m2 = 0.0f;
  float panicle_tip_height_m = 0.0f;
  float vegetative_canopy_height_m = 0.0f;
  float panicle_canopy_clearance_m = 0.0f;
  float panicle_peduncle_length_m = 0.0f;
  float panicle_rachis_length_m = 0.0f;
  float panicle_branch_length_m = 0.0f;
  float middle_parbar_top_elevation_m = 0.0f;
  float vegetative_maturity_gdd = 0.0f;
  float panicle_initiation_gdd = 0.0f;
  float panicle_maturity_gdd = 0.0f;
  float minimum_vegetative_growth_progress = 0.0f;
  float minimum_panicle_growth_progress = 0.0f;
  bool has_geometry = false;
  bool panicle_emerged = false;
  bool vegetative_organs_mature = false;
  bool panicle_mature = false;
  bool all_organs_mature = false;
  std::vector<LSystemAxisPhenotypeRecord> axes;
};

class PyDigitalAgriculture {
 public:
  /**
   * @brief Add SorghumLayer to the framework.
   */
  static void PushSorghumLayer();
  static void RegisterClasses();
  static Entity CreateEntityFromSorghumState(const Handle& sorghum_handle);
  static Entity CreateEntityFromSorghumDescriptor(const Handle& sorghum_handle);
  static Entity CreateEntityFromSorghumGenerator(const Handle& sorghum_generator_handle, int seed);
  static Entity CreateEntityFromSorghumField(const Handle& sorghum_generator_handle, int seed);
  static void ApplySorghumGrid(const Handle& sorghum_field_handle, const Handle& sorghum_generator_handle,
                               const SorghumGrid& sorghum_grid);

  /**
   * @brief Register for python binding.
   * @param m The target python binding module to register functions and classes.
   */
  static void Initialize(pybind11::module& m);

  static void EnableBTF();

  static void SetCBTFGroup(const Handle& cbtf_group_handle);

  static bool CheckBTFComponentsExist();

  static void SetSkyDome();

  static void PushRayTracerLayer();

  static void SetSunDirection(glm::vec3 angles);

  static void IlluminationEstimationOnSorghum();

  static void CheckTriangleEstimator(const Entity& sorghum_entity);

  static Entity InstantiateSorghumField(const Handle& sorghum_field_handle, const Handle& sorghum_coordinates,
                                        const int seed, const int index = 200, const float radius = 2000.0f);

  static std::vector<std::vector<glm::vec3>> GetAllIlluminationEstimationResultsOnSorghum();

  static Handle SetPARSensors(const Entity& sorghum_field);

  static void IlluminationEstimationOnSensors(const Handle& sensor_group_handle);

  static std::vector<std::vector<glm::vec3>> GetAllIlluminationEstimationResultsFromSensors(
      const Handle& sensor_group_handle);

  static void SetIlluminationSamples(int samples, int bounces);

  static bool RunLSystemSorghumProject(const std::filesystem::path& project_path,
                                       const std::filesystem::path& runtime_package_path = {},
                                       const std::filesystem::path& start_scene_path = {},
                                       bool load_project_assets = false);

  static bool WaitForProjectIdle(int max_frames = 30000);

  static void LoopFrames(int frames);

  static bool EnsureIlluminationSoilContext();

  static bool ValidateIlluminationContext();

  static size_t ConfigureSceneReviewLighting(float ambient_light_intensity = 1.25f,
                                             float directional_light_brightness = 1.0f, bool cast_shadows = false);

  static bool ConfigureRayTracerSkydome(glm::vec3 sun_angles_degrees = glm::vec3(55.0f, 30.0f, 0.0f),
                                        float sun_angular_diameter_radians = 0.00918043f, float sun_intensity = 1.0f,
                                        glm::vec3 sun_color = glm::vec3(1.0f), float skylight_intensity = 1.0f,
                                        float ambient_light_intensity = 0.1f, float gamma = 2.2f);

  static bool CaptureCurrentSceneRayTraced(int resolution_x, int resolution_y, const std::filesystem::path& output_path,
                                           int samples = 64, int bounces = 4, float gamma = 2.2f);

  static size_t ConfigurePresentationGroundExtension(bool enabled, float size_m = 160.0f, float texture_repeat_m = 2.0f,
                                                     float grid_spacing_m = 1.0f);

  static std::array<uint64_t, 4> GetRayTracerBuildCounters();

  static size_t GrowSorghumLsPlantsToAdulthood(int seed_base = -1, const std::string& cultivar_filter = "",
                                               bool reuse_geometry_entities = false,
                                               bool update_render_geometry = true);

  static size_t GrowSorghumLsPlantsToGdd(float evaluation_gdd, int seed_base = -1, bool update_render_geometry = true);

  /// Advance a GDD-ordered sequence without replaying each plant from zero.
  static size_t AdvanceSorghumLsPlantsToGdd(float evaluation_gdd, int seed_base = -1,
                                            bool update_render_geometry = true);

  static size_t MaterializeSorghumLsPlantGeometry(bool update_render_geometry = false);

  static size_t SetSorghumLsLeafThickness(float leaf_thickness_m, bool regenerate_geometry = true);

  static size_t SetSorghumLsLeafWidthScale(float leaf_width_scale, bool regenerate_geometry = true);

  static size_t ConfigureSorghumLsLeafMeshQuality(float vertical_subdivision_length, int horizontal_subdivision_step,
                                                  bool bottom_face = true, bool enable_leaf_sheath = true,
                                                  bool regenerate_geometry = false);

  static size_t SetSorghumLsFinalizeSnapshotMorphology(bool enabled);

  /// Clone each active descriptor and replace only reproductive presentation
  /// fields. Vegetative distributions and growth curves remain unchanged.
  static size_t ConfigureSorghumLsPaniclePresentation(float peduncle_length_m, float rachis_length_m,
                                                      float branch_length_m, int primary_branch_count,
                                                      int spikelet_pairs_per_branch, float spikelet_length_m,
                                                      float spikelet_radius_m, float immature_red, float immature_green,
                                                      float immature_blue, float mature_red, float mature_green,
                                                      float mature_blue);

  static size_t SetSorghumLsCultivarDescriptors(const std::filesystem::path& btx_descriptor_path,
                                                const std::filesystem::path& pawaga_descriptor_path,
                                                bool regenerate_geometry = true, int seed_base = -1);

  static size_t SetSorghumLsGenotypeDescriptors(const std::map<std::string, std::filesystem::path>& descriptor_paths,
                                                bool regenerate_geometry = true, int seed_base = -1);

  static size_t SetSorghumLsGridSpacing(float spacing_x, float spacing_z, const std::string& cultivar_filter = "");

  static size_t ConfigureSorghumLsPlantingGrid(const std::vector<std::string>& row_genotypes, uint32_t columns,
                                               float column_spacing_m = 0.76f, float row_spacing_m = 1.10f,
                                               float center_x_m = 2.58f, float center_z_m = -7.51f);

  // Keeps the measured marker coordinates and PARBAR context, but changes the
  // cultivar prefix used when the markers are converted to SorghumLS plants.
  static size_t RelabelSorghumLsPlantingMarkersByRow(const std::vector<std::string>& row_genotypes);

  static size_t ConfigureSorghumLsReplicatedSixByTenProfile(const std::vector<std::string>& block_genotypes);

  static size_t RemoveParbarContext();

  static size_t ConformSorghumLsPlantsToGroundMesh();

  static size_t RemoveSorghumLsPseudoTillerPlants();

  static size_t ConvertSorghumLsPlantsToPlantingMarkers();

  static size_t InstantiateSorghumLsPlantsFromPlantingMarkers();

  static std::vector<LSystemPlantSceneMetadataRecord> GetSorghumLsPlantSceneMetadata(bool measure_geometry = true);

  static size_t MoveParbarMiddlePanelsToPlantHeightFraction(float height_fraction = 2.0f / 3.0f);

  static Handle CreateParbarTopFaceSensorGroup(uint32_t samples_per_panel = 100);

  static void EstimatePARSensors(const Handle& sensor_group_handle, int samples = 64, int bounces = 4,
                                 float push_normal_distance = 0.001f, int seed = 0);

  static std::vector<ParbarProbeRecord> GetParbarTopFaceSensorResults(const Handle& sensor_group_handle,
                                                                      uint32_t samples_per_panel = 100);

  static std::vector<LSystemGridIlluminationRecord> EstimateSorghumLsGridIllumination(
      int samples = 64, int bounces = 4, int max_triangles_per_plant = 0, float push_normal_distance = 0.001f,
      int seed = 0, const std::string& cultivar_filter = "");

  static std::vector<LSystemDescriptorPhenotypeRecord> SampleSorghumLsDescriptorPhenotypes(
      const std::filesystem::path& base_descriptor_path, float leaf_modules_mean, float leaf_modules_deviation,
      float length_mean_scale, float length_deviation_scale, int sample_count = 1000, int seed_base = 0,
      float leaf_width_scale = 1.0f, float main_culm_diameter_m = 0.0f, float tiller_leaf_count_ratio = 0.90f,
      float tiller_height_ratio = 0.90f, bool finalize_snapshot = true, bool include_organs = false,
      float leaf_length_mean_scale = 0.0f, float leaf_length_deviation_scale = 0.0f,
      float leaf_gravity_droop_compliance = -1.0f, float target_gdd = -1.0f);

  static std::vector<LSystemDescriptorPhenotypeRecord> SampleSorghumLsDescriptorAssetPhenotypes(
      const std::filesystem::path& descriptor_path, int sample_count = 1000, int seed_base = 0,
      bool finalize_snapshot = true, bool include_organs = false, float leaf_gravity_droop_compliance = -1.0f);

  static bool SaveCalibratedSorghumLsDescriptor(const std::filesystem::path& base_descriptor_path,
                                                const std::filesystem::path& output_descriptor_path,
                                                float leaf_modules_mean, float leaf_modules_deviation,
                                                float length_mean_scale, float length_deviation_scale,
                                                float leaf_width_scale = 1.0f, float main_culm_diameter_m = 0.0f,
                                                float tiller_leaf_count_ratio = 0.90f,
                                                float tiller_height_ratio = 0.90f, float leaf_length_mean_scale = 0.0f,
                                                float leaf_length_deviation_scale = 0.0f, float target_gdd = -1.0f);

  static bool ScaleSorghumLsDescriptorOrganLengths(const std::filesystem::path& descriptor_path,
                                                   float internode_mean_scale, float internode_deviation_scale,
                                                   float leaf_mean_scale = 1.0f, float leaf_deviation_scale = 1.0f,
                                                   float leaf_gravity_droop_compliance = -1.0f);

  static bool SaveActiveSceneAsProjectAsset(const std::filesystem::path& scene_asset_path);

  static Entity CreateEntityFromPrefab(const Handle& prefab_handle, const glm::vec3& position,
                                       const glm::vec3& euler_rotation, const glm::vec3& scale);
};

}  // namespace py_digital_agriculture_package

#endif
