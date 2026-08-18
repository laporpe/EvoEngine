#pragma once

#include "LSystemComponentBase.hpp"
#include "SorghumGeometrySnapshot.hpp"
#include "SorghumGrowthModel.hpp"
#include "SorghumLeafMesh.hpp"

#include <cstdint>
#include <filesystem>

namespace l_system_package {
using namespace evo_engine;

class SorghumLSDescriptor;

class SorghumLS final : public LSystemComponentBase<SorghumLS> {
 public:
  enum class ColorMode : int {
    Shaded = 0,
    ByType = 1,
    ByInstance = 2,
    ByNode = 3,
    LeafSenescence = 4,
  };

  static void SetGlobalColorMode(ColorMode mode);
  [[nodiscard]] static ColorMode GetGlobalColorMode();

  // Leaf mesh controls.
  SorghumLeafMeshSettings leaf_mesh_settings;
  bool leaf_bottom_face = true;

  // Growth model (runtime only, not serialized).
  SorghumGrowthModel growth_model;

  // Runtime counters/profiling.
  double last_grow_seconds = 0.0;
  double last_rebuild_seconds = 0.0;
  double last_rebuild_internode_seconds = 0.0;
  double last_leaf_spline_seconds = 0.0;
  double last_leaf_mesh_seconds = 0.0;
  double last_mesh_upload_seconds = 0.0;
  uint32_t last_node_count = 0;
  uint32_t last_internode_count = 0;
  uint32_t last_leaf_count = 0;
  uint32_t last_live_leaf_count = 0;
  uint32_t last_panicle_branch_count = 0;
  uint32_t last_panicle_spikelet_count = 0;
  uint32_t last_invalid_instance_count = 0;

  float GetInfancyTargetGDD() const {
    return 0.0f;
  }

  void GenerateGeometryEntities(bool uncapped_growth = false, bool reuse_geometry_entities = false);
  [[nodiscard]] std::shared_ptr<const SorghumGeometrySnapshot> GenerateGeometrySnapshot(bool uncapped_growth = false,
                                                                                        uint32_t max_growth_steps = 0);
  /// Advance an already-initialized plant to target_gdd without replaying its
  /// prior thermal history.  Reinitializes safely when target_gdd is rewound.
  [[nodiscard]] std::shared_ptr<const SorghumGeometrySnapshot> AdvanceGeometrySnapshot(bool uncapped_growth = false,
                                                                                       uint32_t max_growth_steps = 0);
  void GeneratePreviewGeometryEntities(float preview_target_gdd, uint32_t preview_max_growth_steps);
  void GrowToTargetGDD(bool uncapped_growth = false, uint32_t max_growth_steps = 0);
  void SetSeasonalChronologicalMode(bool enable_independent_chronological_clock);
  bool AdvanceChronologicalAging(float delta_years);
  [[nodiscard]] std::shared_ptr<const SorghumGeometrySnapshot> BuildGeometrySnapshot();
  void PublishGeometrySnapshot(const std::shared_ptr<const SorghumGeometrySnapshot>& snapshot,
                               bool update_render_geometry = true);
  void RebuildGeometry();
  void ClearGeometryEntities() const;
  [[nodiscard]] const std::shared_ptr<const SorghumGeometrySnapshot>& GetGeometrySnapshot() const;
  void ExportObj(const std::filesystem::path& path) const;
  void ExportFlowGraph(YAML::Emitter& out);
  void ExportFlowGraph(const std::filesystem::path& path);
  void ExportNodeGraph(YAML::Emitter& out);
  void ExportNodeGraph(const std::filesystem::path& path);

  void Start() override;
  void OnDestroy() override;
  void CollectAssetRef(std::vector<AssetRef>& list);

 private:
  mutable std::shared_ptr<const SorghumGeometrySnapshot> geometry_snapshot_;
  uint64_t geometry_version_ = 0;
};

}  // namespace l_system_package
