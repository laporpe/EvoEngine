#include <gtest/gtest.h>

#include "EvoEngine_SDK_PCH.hpp"

#include "DatasetGeneration_PCH.hpp"
#include "SorghumPointCloudScanner.hpp"

using namespace dataset_generation_package;

TEST(SorghumFractionalCover, GeneratesStratifiedDownwardRaysPerPixel) {
  SorghumFractionalCoverSettings settings;
  settings.center = glm::vec2(1.f, 2.f);
  settings.area_size = glm::vec2(4.f, 2.f);
  settings.resolution = glm::ivec2(2, 1);
  settings.samples_per_pixel_axis = 2;
  settings.scan_height = 7.f;

  std::vector<evo_engine::PointCloudSample> samples;
  settings.GenerateSamples(samples);

  ASSERT_EQ(samples.size(), 8);
  EXPECT_EQ(samples[0].start, glm::vec3(-0.5f, 7.f, 1.5f));
  EXPECT_EQ(samples[3].start, glm::vec3(0.5f, 7.f, 2.5f));
  EXPECT_EQ(samples[4].start, glm::vec3(1.5f, 7.f, 1.5f));
  EXPECT_EQ(samples[7].start, glm::vec3(2.5f, 7.f, 2.5f));
  for (const auto& sample : samples)
    EXPECT_EQ(sample.direction, glm::vec3(0.f, -1.f, 0.f));
}

TEST(SorghumFractionalCover, RejectsInvalidSamplingArea) {
  SorghumFractionalCoverSettings settings;
  settings.area_size.x = 0.f;

  std::vector<evo_engine::PointCloudSample> samples(1);
  settings.GenerateSamples(samples);

  EXPECT_TRUE(samples.empty());
}
