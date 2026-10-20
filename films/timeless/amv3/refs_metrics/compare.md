| metric | ref_a | ref_b | ref_c | v2 |
|---|---|---|---|---|
| frames | 801 | 860 | 637 | 820 |
| transitions (hard + smear) | 34 | 45 | 19 | 44 |
| median shot len (f) | 17.0 | 17.0 | 20.0 | 16.0 |
| still frames % (median flow < 0.5 px/f) | 0.0 | 0.4 | 0.0 | 0.9 |
| longest still run (f) | 0 | 3 | 0 | 3 |
| hold camera speed median (px/f) | 16.85 | 19.58 | 10.55 | 3.44 |
| hold camera speed p10 (px/f) | 4.9 | 5.41 | 3.87 | 1.58 |
| hold mean flow median (px/f) | 20.51 | 22.61 | 14.97 | 4.48 |
| % near-static hold frames (mean flow < 4 px/f) | 2.5 | 1.2 | 2.0 | 44.6 |
| longest near-static run (f) | 2 | 4 | 2 | 28 |
| hold zoom rate median (%/f) | 2.47 | 2.05 | 2.1 | 0.39 |
| hold roll median (deg/f) | 0.09 | 0.12 | 0.054 | 0.021 |
| camera speed jump ratio p95 (outside cuts) | 2.196 | 3.022 | 2.089 | 2.354 |
| % frames camera speed jumps > x1.35 | 18.6 | 27.2 | 17.8 | 14.2 |
| picture speed (mean flow) jump ratio p95 | 2.017 | 1.837 | 1.854 | 2.289 |
| picture speed jump max | 7.12 | 4.98 | 4.06 | 13.43 |
| % frames picture speed jumps > x1.35 | 21.5 | 25.1 | 19.4 | 15.9 |
| % duplicated frames | 3.2 | 0.0 | 0.0 | 0.0 |
| smear frames per cut (median) | 9.0 | 3.0 | 10.0 | 4.0 |
| % cuts with >= 2 smear frames | 88.2 | 73.3 | 94.7 | 68.2 |
| % hard cuts (0 smear) | 11.8 | 17.8 | 0.0 | 31.8 |
| frames after cut until B is legible, sharp_rel >= 0.5 (median) | 7.5 | 0.0 | 8.0 | 3.0 |
| frames after cut until B is sharp, sharp_rel >= 0.8 (median) | 8.0 | 5.0 | 11.0 | 4.0 |
| re-sharpen max | 13 | 13 | 13 | 12 |
| cut peak flow (px/f, median) | 190.2 | 224.2 | 154.0 | 151.0 |
| acceleration into cut (x per frame, median) | 1.62 | 1.42 | 1.36 | 1.62 |
| deceleration after cut (x per frame, median) | 1.24 | 1.17 | 1.25 | 1.31 |
| worst 1-frame speed step into a cut (median) | 2.48 | 2.32 | 2.27 | 3.26 |
| worst 1-frame speed drop out of a cut (median) | 2.16 | 1.76 | 2.03 | 3.29 |
| worst 1-frame speed drop out of a cut (p90) | 3.75 | 3.04 | 3.05 | 10.08 |
| speed after / before cut (median) | 1.06 | 1.3 | 1.26 | 1.37 |
| % cuts with speed step outside x0.5-x2 | 17.2 | 40.9 | 33.3 | 37.2 |
| zoom direction across cut | {'push->push': 11, 'pull->pull': 12, 'push->pull': 2, 'pull->push': 0, 'null': 9} | {'push->push': 9, 'pull->pull': 13, 'push->pull': 2, 'pull->push': 0, 'null': 21} | {'push->push': 3, 'pull->pull': 6, 'push->pull': 2, 'pull->push': 0, 'null': 8} | {'push->push': 4, 'pull->pull': 6, 'push->pull': 11, 'pull->push': 1, 'null': 22} |
| % zoom cuts that reverse the zoom sign | 8.0 | 8.3 | 18.2 | 54.5 |
| % frames fit failed | 19.1 | 24.4 | 14.6 | 8.7 |
