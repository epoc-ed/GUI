import numpy as np

def super_gaussian2d_rotated(x, y, amplitude, xo, yo, sigma_x, sigma_y, theta, n):
    """
    Rotated 2D Super-Gaussian function.

    (x, y): coordinate grids
    amplitude: peak amplitude
    xo, yo: center coordinates
    sigma_x, sigma_y: standard deviations along x and y axes
    theta: rotation angle in radians
    n: order of the super-Gaussian (n=2 corresponds to Gaussian)
    """
    x0 = xo
    y0 = yo
    a = (np.cos(theta)**2) / (2 * sigma_x**2) + (np.sin(theta)**2) / (2 * sigma_y**2)
    b = -np.sin(2 * theta) / (4 * sigma_x**2) + np.sin(2 * theta) / (4 * sigma_y**2)
    c = (np.sin(theta)**2) / (2 * sigma_x**2) + (np.cos(theta)**2) / (2 * sigma_y**2)
    x_diff = x - x0
    y_diff = y - y0
    exponent = ((a * x_diff**2 + 2 * b * x_diff * y_diff + c * y_diff**2)) ** (n / 2)
    return amplitude * np.exp(-exponent)

from lmfit import Model, Parameters
images = np.load("/home/ferjao_k/mini_symposium/autofocus_006.npy")

im = images[0]

roi_start_row = 93
roi_end_row = 293
roi_start_col = 326
roi_end_col = 535
im_roi = im[roi_start_row:roi_end_row+1, roi_start_col:roi_end_col+1]

n_columns_roi, n_rows_roi = im_roi.shape[1], im_roi.shape[0]

total_intensity = im_roi.sum()

# Weighted average of the columns indices (xo_init)
col_sums = im_roi.sum(axis=0)  # Sum along the rows (column-wise sum)
linspace_cols = np.linspace(0, n_columns_roi-1, n_columns_roi) 
xo_init = np.dot(col_sums, linspace_cols) / total_intensity

# Weighted average of the rows indices (yo_init)
row_sums = im_roi.sum(axis=1)  # Sum along the columns (row-wise sum)
linspace_rows = np.linspace(0, n_rows_roi-1, n_rows_roi) 
yo_init = np.dot(row_sums, linspace_rows) / total_intensity

diag_roi = np.sqrt(n_columns_roi*n_columns_roi+n_rows_roi*n_rows_roi)

x_roi, y_roi = np.meshgrid(np.arange(n_columns_roi), np.arange(n_rows_roi))
z_flat_roi = im_roi.ravel()
x_flat_roi = x_roi.ravel()
y_flat_roi = y_roi.ravel()

# Create model and parameters for ROI fitting
model_roi = Model(super_gaussian2d_rotated, independent_vars=['x', 'y'], nan_policy='omit')
params_roi = Parameters()
params_roi.add('amplitude', value=np.max(im_roi), min=1, max=10 * np.max(im_roi))
params_roi.add('xo', value=xo_init, min=0, max=n_columns_roi)
params_roi.add('yo', value=yo_init, min=0, max=n_rows_roi)
params_roi.add('sigma_x', value=n_columns_roi // 4, min=1, max=diag_roi // 2)
params_roi.add('sigma_y', value=n_rows_roi // 4, min=1, max=diag_roi // 2)
params_roi.add('theta', value=0, min=-np.pi / 2, max=np.pi / 2)
params_roi.add('n', value=2, min=1, max=10)  # Adjust 'n' as needed

result_roi = model_roi.fit(z_flat_roi, x=x_flat_roi, y=y_flat_roi, params=params_roi)

import matplotlib.pyplot as plt

# Reshape the fitted data to the ROI shape
fitted_data = model_roi.eval(params=result_roi.params, x=x_roi, y=y_roi)

# Choose the row index for profile visualization
row_index = n_rows_roi // 2  # For example, the middle row

# Extract data along the row index
data_row = im_roi[row_index, :]
fit_row = fitted_data[row_index, :]
x_axis = np.arange(n_columns_roi)

# Create a figure with 2x2 subplots
fig, axs = plt.subplots(2, 2, figsize=(12, 10))

# Original ROI image
axs[0, 0].set_title('Original ROI')
im0 = axs[0, 0].imshow(im_roi, origin='lower', extent=(0, n_columns_roi, 0, n_rows_roi))
fig.colorbar(im0, ax=axs[0, 0])

# Add horizontal line at the selected row_index on the original ROI image
axs[0, 0].axhline(y=row_index, color='yellow', linestyle='--', linewidth=1)

# Fitted model image
axs[0, 1].set_title('Fitted Supper Gaussian Model')
im1 = axs[0, 1].imshow(fitted_data, origin='lower', extent=(0, n_columns_roi, 0, n_rows_roi))
fig.colorbar(im1, ax=axs[0, 1])

# Add horizontal line at the selected row_index on the fitted model image
axs[0, 1].axhline(y=row_index, color='yellow', linestyle='--', linewidth=1)

# Profile of image data at the selected row index
axs[1, 0].set_title(f'Image Profile at Row {row_index}')
axs[1, 0].plot(x_axis, data_row, 'b-', label='Data')
axs[1, 0].set_xlabel('Column Index')
axs[1, 0].set_ylabel('Intensity')
axs[1, 0].legend()
axs[1, 0].grid(True)

# Profile of fitted data at the same row index
axs[1, 1].set_title(f'Fitted Profile at Row {row_index}')
axs[1, 1].plot(x_axis, fit_row, 'r--', label='Fit')
axs[1, 1].set_xlabel('Column Index')
axs[1, 1].set_ylabel('Intensity')
axs[1, 1].legend()
axs[1, 1].grid(True)

plt.tight_layout()
plt.show()