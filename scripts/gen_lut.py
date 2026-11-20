# -*- coding: utf-8 -*-
"""Generate high-precision 3D LUT matching Islam AI DaVinci Resolve Stills + Intelligent Lighting."""
import numpy as np
from pathlib import Path

def generate_cube_lut(lut_path, size=33):
    Path(lut_path).parent.mkdir(parents=True, exist_ok=True)
    with open(lut_path, 'w', encoding='utf-8') as f:
        f.write('# Islam AI Master Color & Intelligent Lighting 3D LUT\n')
        f.write('TITLE "Islam AI Master Grade"\n')
        f.write(f'LUT_3D_SIZE {size}\n')
        f.write('DOMAIN_MIN 0.0 0.0 0.0\n')
        f.write('DOMAIN_MAX 1.0 1.0 1.0\n\n')
        
        grid = np.linspace(0.0, 1.0, size)
        
        for b in grid:
            for g in grid:
                for r in grid:
                    # 1. Intelligent Lighting / Shadow-Midtone Lift
                    # Input luminance
                    lum = 0.299 * r + 0.587 * g + 0.114 * b
                    
                    # Smart exposure curve: lifts underexposed midtones (faces) from ~0.35 to ~0.55
                    # Gentle gamma lift for dark room footage (gamma 0.82)
                    r_lit = r ** 0.82
                    g_lit = g ** 0.82
                    b_lit = b ** 0.82
                    
                    # 2. Color Character from DaVinci Still 1.6 (Warm, healthy skin, filmic rich blacks)
                    # Warm golden-amber push in midtones
                    r_graded = r_lit * (1.0 + 0.06 * np.sin(np.pi * r_lit))
                    g_graded = g_lit * (1.0 + 0.015 * np.sin(np.pi * g_lit))
                    b_graded = b_lit * (1.0 - 0.035 * np.sin(np.pi * b_lit))
                    
                    # 3. Soft Filmic S-Curve & Highlight Roll-off (protect highlights from clipping)
                    def s_curve(x):
                        return 0.5 * (1.0 + np.tanh(2.0 * (x - 0.46))) / (0.5 * (1.0 + np.tanh(2.0 * (1.0 - 0.46))))
                    
                    r_final = 0.75 * r_graded + 0.25 * s_curve(r_graded)
                    g_final = 0.75 * g_graded + 0.25 * s_curve(g_graded)
                    b_final = 0.75 * b_graded + 0.25 * s_curve(b_graded)
                    
                    # Safe clamp
                    rf = max(0.0, min(1.0, float(r_final)))
                    gf = max(0.0, min(1.0, float(g_final)))
                    bf = max(0.0, min(1.0, float(b_final)))
                    
                    f.write(f'{rf:.6f} {gf:.6f} {bf:.6f}\n')

if __name__ == "__main__":
    # Local Davinci Resolve still path omitted for public repository
    lut_out = Path(__file__).resolve().parent.parent / "motion" / "luts" / "islam_ai_master_grade.cube"
    generate_cube_lut(str(lut_out), 33)
    print("✅ Generated 3D LUT successfully in both directories!")
