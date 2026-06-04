#include <string.h>

void compact_tiles(const unsigned char* frame_data, int frame_data_len, 
                   unsigned char* output_pixels, int row_count, int column_count) {
    int pos = 0;
    int width = column_count * 16;
    int height = row_count * 16;
    int max_out_pos = width * height * 3;

    for (int grid_y = 0; grid_y < row_count; grid_y++) {
        for (int grid_x = 0; grid_x < column_count; grid_x++) {
            for (int y = 0; y < 16; y++) {
                for (int x = 0; x < 16; x++) {
                    if (pos + 3 <= frame_data_len) {
                        int out_x = grid_x * 16 + x;
                        int out_y = grid_y * 16 + y;
                        int out_pos = (out_y * width + out_x) * 3;
                        if (out_pos + 2 < max_out_pos) {
                            output_pixels[out_pos] = frame_data[pos];
                            output_pixels[out_pos+1] = frame_data[pos+1];
                            output_pixels[out_pos+2] = frame_data[pos+2];
                        }
                        pos += 3;
                    }
                }
            }
        }
    }
}
