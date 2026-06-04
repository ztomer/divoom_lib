#include <arm_neon.h>

void compact_tiles(const unsigned char* frame_data, int frame_data_len, 
                   unsigned char* output_pixels, int row_count, int column_count) {
    int width = column_count * 16;
    int height = row_count * 16;
    int max_out_pos = width * height * 3;

    int tile_idx = 0;
    for (int grid_y = 0; grid_y < row_count; grid_y++) {
        for (int grid_x = 0; grid_x < column_count; grid_x++) {
            for (int y = 0; y < 16; y++) {
                int in_pos = (tile_idx * 16 + y) * 16 * 3;
                int out_x = grid_x * 16;
                int out_y = grid_y * 16 + y;
                int out_pos = (out_y * width + out_x) * 3;
                
                // Explicitly copy an entire 16-pixel row (48 bytes) using three 128-bit vector registers.
                if (in_pos + 48 <= frame_data_len && out_pos + 48 <= max_out_pos) {
                    uint8x16_t v0 = vld1q_u8(frame_data + in_pos);
                    uint8x16_t v1 = vld1q_u8(frame_data + in_pos + 16);
                    uint8x16_t v2 = vld1q_u8(frame_data + in_pos + 32);

                    vst1q_u8(output_pixels + out_pos, v0);
                    vst1q_u8(output_pixels + out_pos + 16, v1);
                    vst1q_u8(output_pixels + out_pos + 32, v2);
                }
            }
            tile_idx++;
        }
    }
}

