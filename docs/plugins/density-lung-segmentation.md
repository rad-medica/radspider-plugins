# Density lung segmentation

Plugin id: `org.radspider.density-lung-segmentation` · folder: [`../../org.radspider.density-lung-segmentation`](../../org.radspider.density-lung-segmentation)

TL;DR: the *Lung CT GMM Segmentation* module of the 3D Slicer extension **DensityLungSegmentation** (P. Zaffino et
al., [pzaffino/SlicerDensityLungSegmentation](https://github.com/pzaffino/SlicerDensityLungSegmentation), read at
commit `cd207de`): a lung mask by threshold and morphology, then each voxel inside gets the most likely of five
density classes of a **fixed** Gaussian mixture fitted on COVID-19 CTs. Re-implemented with numpy and scipy. CT in HU
only. **Not clinically evaluated.**

| Entry | Does | Slicer equivalent |
|---|---|---|
| segmentation *gmm* | Five segments, one class per voxel | Output segmentation |
| segmentation *gmm_averaged* | The same after a 4 × 4 × 4 voxel median of the labels | Averaged output segmentation |
| tool *volumes* | The same (param *averaged* 0 / 1) with volume in ml, share of the lung mask and mean HU per class, a bar chart and the segments | — (ours) |

| Label | Segment | Mixture: weight, mean HU, SD HU | Wins for HU |
|---|---|---|---|
| 1 | Air | 0.339, −950.4, 44.0 | below −893.5 |
| 2 | Healthy lungs | 0.362, −829.0, 58.4 | −893.5 … −721 |
| 3 | Ground glass opacity | 0.139, −652.3, 94.5 | −721 … −472 |
| 4 | Consolidation | 0.055, −337.0, 156.7 | −472 … −235 |
| 5 | Other denser tissues | 0.106, −12.5, 194.0 | −235 and above |

The mixture parameters are the `weights_`, `means_` and `covariances_` stored in upstream's
`LungCTGMMSegmentation/Resources/GMM_parameters_COVID-19.joblib` (a scikit-learn `GaussianMixture`, 5 components,
1 feature; SHA-256 `05297ccedfc8e4d9750a2d4e56a2e077b521c54367b8a48e713e0e19082adc12`), read out of the file without
unpickling it and kept as constants in `plugin.py`. The "wins for" limits follow from them (computed in 0.5 HU
steps); upstream has no explicit thresholds for the classes.

| Item | |
|---|---|
| Model | The fixed mixture above; nothing is fitted to the series, nothing is downloaded, no pickle is loaded, scikit-learn and joblib are not needed. Paper: Zaffino et al., "An Open-Source COVID-19 CT Dataset with Automatic Lung Tissue Classification for Radiomics", Bioengineering 8(2):26, 2021 |
| Pipeline | As `LungCTGMMSegmentationLogic.run` in `LungCTGMMSegmentation/LungCTGMMSegmentation.py`: (1) HU below −1000 set to −1000. (2) Air = HU < **−155**, binary opening, 3 iterations (`threshold_image`). (3) 3D islands of at least **500 000 voxels** whose bounding box does not reach the first or last row or column are lung; the rest (the air around the patient, small pockets) is dropped (`extract_only_lungs_islands`). (4) Closing with a ball of **30** then **20 voxels** on the lungs' bounding box (`close_lungs_mask`); 1000 voxels or fewer → error. (5) Most likely mixture component per voxel of the mask, labels 1–5 by rising mean. (6) Averaged output: median filter of size **4** on the labels |
| Params | *Lung threshold* (−155 HU) and *Smallest lung island* (500 000 voxels) are upstream's constants made adjustable: the island size is in voxels, so a thick-slice or small series needs a lower one, and the error says so |
| Differences from upstream | (1) Closing by two Euclidean distance transforms instead of SimpleITK's kernel: the same operation with an exact ball, whereas ITK's ball element is a slightly different digital ball, so the mask edge can differ by a voxel. (2) Upstream's island loop runs `range(nb_labels)` over labels `0 … nb_labels` and so never looks at the last island; here every island is looked at. (3) Upstream's bounding box drops the last slice, row and column of the lungs (exclusive slice end); not copied. (4) The median runs on the box around the mask (4 voxel margin) instead of the whole volume: same result, less time. (5) No data (NaN) is treated as −1000 HU |
| Limits | Units: a series that is not in HU is refused (also one with no unit). The closing radii are in **voxels**, not mm, so the mask depends on the voxel size; at 30 voxels it bridges the two lungs and holds hila, vessels, part of the mediastinum and of the chest wall between lung concavities: those are class 5, which is why upstream calls it "other denser tissues", and its volume is not a lung finding. The opening removes thin lung parts (tips, a few voxels thick), the closing does not bring them all back. Lung that is consolidated up to the pleura is not air below −155 HU: it is in the mask only if the closing happens to cover it. Mixture fitted on COVID-19 CTs of one dataset: kernel, slice thickness and contrast shift the classes. "Air" (below −893.5 HU) is airways and over-inflated or emphysematous lung alike |
| Speed | Synthetic 512 × 512 × 300 volume (lungs of 6.0 and 5.2 M voxels), 4 CPU cores: *gmm* 29 s, *gmm_averaged* 34 s, peak memory 3.2 GB (the distance transforms on the lungs' box are float64) |
| Licence | Plugin: own code. Upstream DensityLungSegmentation: **Apache-2.0** (`LICENSE` and README in its repository; no `NOTICE` file). No upstream source is copied; the 15 mixture parameters are taken from its Apache-2.0 model file, credited here and in `plugin.py`. numpy, scipy: BSD-3-Clause, from pip |
| Verified | **Synthetic volumes only, entries called through the SDK's request handler (`radspider_plugin._handle`) in a plain Python 3.13 venv (numpy 2.5.4, scipy 1.18.1) outside the viewer. Not run in radspider, not on real CT, not compared with 3D Slicer's output.** Phantom: 260 × 200 × 100 voxels of 0.8 × 0.8 × 2 mm, body ellipsoid at 40 HU in −1000 HU air, two ellipsoid lungs at −850 HU (over 500 000 voxels each) with box patches at −980, −600, −300 and 0 HU and one isolated −300 HU voxel. *gmm* with defaults: inside the lungs the voxel count of classes 1, 3, 4, 5 equals the known patch counts (4000, 7500, 2561, 1152) and every patch voxel has its class; class 2 is all other lung voxels except 276 at the ellipsoids' tips that the opening removes (checked to be exactly such voxels); nothing outside the body is labelled; the closed mask adds 66 435 voxels of 40 HU tissue between the lungs, all class 5. *gmm_averaged*: the isolated voxel becomes class 2, patch cores keep their class. *volumes*: table cells, bars and segments equal those label volumes, mean HU of the patches as built. Small phantom (160 × 120 × 80): refused at 500 000 voxels with the hint, segmented at 20 000. Mixture classification compared with scikit-learn's `GaussianMixture.predict` (model rebuilt from the constants, not unpickled) on 216 000 values from −1000 to 3000 HU: identical; the variances agree with the `precisions_cholesky_` stored in the file. Every entry refuses `SUVbw` and no unit |
