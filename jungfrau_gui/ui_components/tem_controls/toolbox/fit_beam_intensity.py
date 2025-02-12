import logging
import numpy as np
import pyqtgraph as pg
from pathlib import Path
from PySide6 import QtWidgets
from lmfit import Model, Parameters
from scipy.interpolate import griddata
from line_profiler import LineProfiler

from .... import globals

def filter_outliers(im_roi, lower_percentile=1, upper_percentile=99.99):
    """
    Filter outliers based on percentile thresholds in an image ROI.
    
    Parameters:
        im_roi (np.array): The image region of interest as a numpy array of floats.
        lower_percentile (int): The lower percentile threshold to remove outliers.
        upper_percentile (int): The upper percentile threshold to remove outliers.
        
    Returns:
        np.array: The image ROI with outliers filtered out.
    """
    # Determine lower and upper bounds based on percentiles
    lower_bound = np.percentile(im_roi, lower_percentile)
    upper_bound = np.percentile(im_roi, upper_percentile)
    
    # Find median value for possible substitution
    median_value = np.median(im_roi)
    
    # Create a masked array where outliers are replaced by the median value
    filtered_im_roi = np.where((im_roi < lower_bound) | (im_roi > upper_bound), median_value, im_roi)
    
    return filtered_im_roi

# Define a rotated 2D Gaussian function
def gaussian2d_rotated(x, y, amplitude, xo, yo, sigma_x, sigma_y, theta):
    xo = float(xo)
    yo = float(yo)    
    a = (np.cos(theta)**2)/(2*sigma_x**2) + (np.sin(theta)**2)/(2*sigma_y**2)
    b = -(np.sin(2*theta))/(4*sigma_x**2) + (np.sin(2*theta))/(4*sigma_y**2)
    c = (np.sin(theta)**2)/(2*sigma_x**2) + (np.cos(theta)**2)/(2*sigma_y**2)
    g = amplitude * np.exp( - (a * ((x-xo)**2) + 2 * b * (x-xo) * (y-yo) + c * ((y-yo)**2)))
    return g.ravel()

# Example of ROI array
# roi = [[156,355],[412,611]]
# roi_start_row = 156
# roi_end_row = 355
# roi_start_col = 412
# roi_end_col = 611

def fit_2d_gaussian_roi_NaN(im, roi_start_row, roi_end_row, roi_start_col, roi_end_col):
    """Fit a rotated 2D Gaussian to an ROI of `im`, ignoring NaN (masked) pixels."""
    # Extract the ROI
    im_roi = im[roi_start_row : roi_end_row + 1,
                roi_start_col : roi_end_col + 1]
    
    # Set up x,y mesh for ROI
    n_rows_roi, n_cols_roi = im_roi.shape
    x_roi, y_roi = np.meshgrid(
        np.arange(n_cols_roi), 
        np.arange(n_rows_roi)
    )

    # Flatten
    z_flat_roi = im_roi.ravel()
    x_flat_roi = x_roi.ravel()
    y_flat_roi = y_roi.ravel()

    # ------------------------------------------------
    # 1) Exclude any NaN entries in z_flat_roi
    # ------------------------------------------------
    valid_mask = ~np.isnan(z_flat_roi)
    z_flat_roi_clean = z_flat_roi[valid_mask]
    x_flat_roi_clean = x_flat_roi[valid_mask]
    y_flat_roi_clean = y_flat_roi[valid_mask]

    # Optionally also exclude infinities, just in case
    valid_mask_inf = np.isfinite(z_flat_roi_clean)
    z_flat_roi_clean = z_flat_roi_clean[valid_mask_inf]
    x_flat_roi_clean = x_flat_roi_clean[valid_mask_inf]
    y_flat_roi_clean = y_flat_roi_clean[valid_mask_inf]

    # Now ensure we have some data left
    if len(z_flat_roi_clean) == 0:
        raise ValueError("No valid data left in ROI after removing NaNs/infs. Cannot fit.")

    # ------------------------------------------------
    # 2) Compute initial guesses
    # ------------------------------------------------
    total_intensity = np.nansum(z_flat_roi_clean)
    # Weighted averages (x, y) for initial guess
    # (Note we must use the cleaned arrays)
    # x_flat_roi_clean, y_flat_roi_clean are relative to the ROI.
    col_sums = np.nansum(im_roi, axis=0)  # sum along rows
    row_sums = np.nansum(im_roi, axis=1)  # sum along columns
    # Weighted average index in X (across columns):
    linspace_cols = np.arange(n_cols_roi)
    if col_sums.sum() != 0:
        xo_init = np.dot(col_sums, linspace_cols) / col_sums.sum()
    else:
        xo_init = n_cols_roi/2
    # Weighted average index in Y (across rows):
    linspace_rows = np.arange(n_rows_roi)
    if row_sums.sum() != 0:
        yo_init = np.dot(row_sums, linspace_rows) / row_sums.sum()
    else:
        yo_init = n_rows_roi/2

    amp_guess = 0.5 * np.nanmax(im_roi)  # might be NaN if ROI all NaN, but we handled that case above
    if np.isnan(amp_guess) or amp_guess < 1:
        amp_guess = 1.0

    diag_roi = np.sqrt(n_rows_roi**2 + n_cols_roi**2)

    # ------------------------------------------------
    # 3) Create the model and parameters
    # ------------------------------------------------
    model_roi = Model(
        gaussian2d_rotated, 
        independent_vars=['x','y'],
    )

    params_roi = Parameters()
    params_roi.add('amplitude', value=amp_guess, min=1, max=1.0 * np.nanmax(im_roi))
    params_roi.add('xo', value=xo_init, min=0, max=n_cols_roi)
    params_roi.add('yo', value=yo_init, min=0, max=n_rows_roi)
    params_roi.add('sigma_x', value=max(n_cols_roi//4, 1), min=1, max=diag_roi/2)
    params_roi.add('sigma_y', value=max(n_rows_roi//4, 1), min=1, max=diag_roi/2)
    params_roi.add('theta', value=0, min=-np.pi/2, max=np.pi/2)

    # ------------------------------------------------
    # 4) Perform the fit on the cleaned data
    # ------------------------------------------------
    result_roi = model_roi.fit(
        z_flat_roi_clean,
        x=x_flat_roi_clean,
        y=y_flat_roi_clean,
        params=params_roi
    )

    # Adjust the best-fit center to the full image coordinates
    result_roi.best_values['xo'] += (roi_start_col + 0.5)
    result_roi.best_values['yo'] += (roi_start_row + 0.5)

    # Ensure sigma_x >= sigma_y for a consistent convention (optional)
    if result_roi.best_values['sigma_x'] < result_roi.best_values['sigma_y']:
        sx = result_roi.best_values['sigma_x']
        sy = result_roi.best_values['sigma_y']
        result_roi.best_values['sigma_x'] = sy
        result_roi.best_values['sigma_y'] = sx
        result_roi.best_values['theta'] += np.pi/2

    # Keep angle between [-90, +90) degrees, etc.
    if result_roi.best_values['theta'] > np.pi/2:
        result_roi.best_values['theta'] -= np.pi
    elif result_roi.best_values['theta'] < -np.pi/2:
        result_roi.best_values['theta'] += np.pi

    # Convert theta to degrees
    result_roi.best_values['theta'] = np.degrees(result_roi.best_values['theta'])

    return result_roi

# @profile
def fit_2d_gaussian_roi(im, roi_start_row, roi_end_row, roi_start_col, roi_end_col):
    print(f"***** roi_start_row = {roi_start_row}")    
    print(f"***** roi_end_row = {roi_end_row}")
    print(f"***** roi_start_col = {roi_start_col}")
    print(f"***** roi_end_col = {roi_end_col}")

    im_roi = im[roi_start_row:roi_end_row+1, roi_start_col:roi_end_col+1]
    print(f"++++++np.max(im_roi) = {np.max(im_roi)}")
    print(im_roi)
    # filtered_im_roi = filter_outliers(im_roi) # remove outliers
    # mean_intensity = np.mean(filtered_im_roi)
    # std_intensity = np.std(filtered_im_roi)
    # adaptive_factor = mean_intensity + 2 * std_intensity

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

    print(f'***** x_flat_roi.shape = {x_flat_roi.shape}')
    print(f'***** y_flat_roi.shape = {y_flat_roi.shape}')
    print(f'***** z_flat_roi.shape = {z_flat_roi.shape}')

    # Create model and parameters for ROI fitting
    model_roi = Model(gaussian2d_rotated, independent_vars=['x','y']) #, nan_policy='omit')
    params_roi = Parameters()
    # params_roi.add('amplitude', value=np.max(im_roi), min=1, max=1.2*np.max(filtered_im_roi))
    params_roi.add('amplitude', value=0.5*np.max(im_roi), min=1, max=1.0*np.max(im_roi))
    params_roi.add('xo', value=xo_init, min=0, max=n_columns_roi)
    params_roi.add('yo', value=yo_init, min=0,max=n_rows_roi)
    params_roi.add('sigma_x', value=n_columns_roi//4, min=1, max=diag_roi//2)  # Adjusted for likely ROI size
    params_roi.add('sigma_y', value=n_rows_roi//4, min=1, max=diag_roi//2)    # Adjusted for likely ROI size
    params_roi.add('theta', value=0, min=-np.pi/2, max=np.pi/2)

    result_roi = model_roi.fit(z_flat_roi, x=x_flat_roi, y=y_flat_roi, params=params_roi)
    fit_result = result_roi

    fit_result.best_values['xo'] +=  roi_start_col+0.5
    fit_result.best_values['yo'] +=  roi_start_row+0.5

    if fit_result.best_values['sigma_x'] < fit_result.best_values['sigma_y']:
        fit_result.best_values['sigma_x'], fit_result.best_values['sigma_y'] = fit_result.best_values['sigma_y'], fit_result.best_values['sigma_x']
        fit_result.best_values['theta'] += np.pi/2

    if fit_result.best_values['theta'] > np.pi/2:
        fit_result.best_values['theta'] -= np.pi
    elif fit_result.best_values['theta'] < -np.pi/2:
        fit_result.best_values['theta'] += np.pi

    fit_result.best_values['theta'] =  fit_result.best_values['theta']*180 / np.pi

    return fit_result

def fit_2d_gaussian_roi_test(im, roi):
    
    roiPos = roi.pos()
    roiSize = roi.size()
    roi_start_row = int(np.floor(roiPos.y()))
    roi_end_row = int(np.ceil(roiPos.y() + roiSize.y()))
    roi_start_col = int(np.floor(roiPos.x()))
    roi_end_col = int(np.ceil(roiPos.x() + roiSize.x()))

    logging.debug(f"type(im) is {type(im[0,0])}")

    im_roi = im[roi_start_row:roi_end_row, roi_start_col:roi_end_col]
    logging.debug(f"type(im_roi) is {type(im_roi[0,0])}")

    n_columns_roi, n_rows_roi = im_roi.shape[1], im_roi.shape[0]

    diag_roi = np.sqrt(n_columns_roi*n_columns_roi+n_rows_roi*n_rows_roi)
    
    x_roi, y_roi = np.meshgrid(np.arange(n_columns_roi), np.arange(n_rows_roi))
    z_flat_roi = im_roi.ravel()
    x_flat_roi = x_roi.ravel()
    y_flat_roi = y_roi.ravel()

    # Create model and parameters for ROI fitting
    model_roi = Model(gaussian2d_rotated, independent_vars=['x','y'], nan_policy='omit')
    params_roi = Parameters()
    params_roi.add('amplitude', value=np.max(im_roi), min=1, max=1.2*np.max(im_roi))
    params_roi.add('xo', value=n_columns_roi//2, min=0, max=n_columns_roi)
    params_roi.add('yo', value=n_rows_roi//2, min=0,max=n_rows_roi)
    params_roi.add('sigma_x', value=n_columns_roi//4, min=1, max=diag_roi//2)  # Adjusted for likely ROI size
    params_roi.add('sigma_y', value=n_rows_roi//4, min=1, max=diag_roi//2)    # Adjusted for likely ROI size
    params_roi.add('theta', value=0, min=-np.pi/2, max=np.pi/2)

    result_roi = model_roi.fit(z_flat_roi, x=x_flat_roi, y=y_flat_roi, params=params_roi)
    fit_result = result_roi
    fit_result.best_values['xo'] +=  roi_start_col
    fit_result.best_values['yo'] +=  roi_start_row

    return fit_result

def do_fit_3d(images_3d):
    images_2d = images_3d[0]
    return do_fit_2d(images_2d)

def do_fit_2d(z):
    n_columns = z.shape[1]
    n_rows = z.shape[0]

    x, y = np.meshgrid(np.arange(n_columns), np.arange(n_rows))
    
    X = np.copy(x)
    Y = np.copy(y)

    logging.debug(f'******* The shape of X is {X.shape}')
    logging.debug(X)
    logging.debug(f'******* The shape of Y is {Y.shape}')
    logging.debug(Y)

    z = z.ravel()
    x = x.ravel()
    y = y.ravel()
    
    image_data = griddata((x, y), z, (X, Y), method='linear', fill_value=0)
    logging.debug(f'******* The shape of image_data is {image_data.shape}')

    # Create a model from the Gaussian function
    model = Model(gaussian2d_rotated, independent_vars=['x', 'y'])

    # Create parameters with initial guesses
    params = Parameters()
    params.add('amplitude', value=np.max(image_data), min=0)
    params.add('xo', value=n_columns//2)
    params.add('yo', value=n_rows//2)
    params.add('sigma_x', value=n_columns//4, min=1)
    params.add('sigma_y', value=n_rows//4, min=1)
    params.add('theta', value=0, min=-np.pi/2, max=np.pi/2)

    # Fit the model to the data
    result = model.fit(z, x=x, y=y, params=params)

    # Print the fitting results
    logging.debug(result.fit_report())

    return model, result, image_data, X, Y

# Start the Qt event loop
if __name__ == '__main__':
    format = "%(message)s"
    logging.basicConfig(format=format, level=logging.INFO)
    # Importing data
    path = Path("/home/l_khalil/GUI/")
    images = np.load(path/"Image_data_0.npy")
    model, result, image_data, X, Y = do_fit_3d(images)
    # Initialize the Qt app
    app = QtWidgets.QApplication([])
    # Function to create a color map
    def create_colormap(color):
        colormap = pg.ColorMap(pos=np.linspace(0.0, 1.0, 3), color=[(0,0,0), color, (255,255,255)])
        return colormap.getLookupTable(0.0, 1.0, 256)
    # Choose your color
    color = (255, 0, 0)  # Red color
    # Create a window
    win = pg.GraphicsLayoutWidget(show=True, title="Gaussian Fit Visualization")
    win.resize(500, 900)
    # Data Plot
    dataPlot = win.addPlot(title="Data")
    dataImage = pg.ImageItem(axisOrder='row-major')
    dataImage.setLookupTable(create_colormap(color))
    dataPlot.addItem(dataImage)
    dataImage.setImage(image_data)
    dataPlot.setLabels(left='y', bottom='x')
    dataPlot.setRange(xRange=(0, globals.ncol), yRange=(0, globals.nrow))
    # Fit Plot
    win.nextRow()  # Move to the next row for the next plot
    fitPlot = win.addPlot(title="Fit")
    fitImage = pg.ImageItem(axisOrder='row-major')
    fitImage.setLookupTable(create_colormap(color))
    fitPlot.addItem(fitImage)
    fit = model.func(X, Y, **result.best_values).reshape(*X.shape)
    fitImage.setImage(fit) 
    fitPlot.setLabels(left='y', bottom='x')
    fitPlot.setRange(xRange=(0, globals.ncol), yRange=(0, globals.nrow))
    # Data - Fit Plot
    win.nextRow()  # Move to the next row for the next plot
    diffPlot = win.addPlot(title="Data - Fit")
    diffImage = pg.ImageItem(axisOrder='row-major')
    diffImage.setLookupTable(create_colormap(color))
    diffPlot.addItem(diffImage)
    diffImage.setImage(image_data - fit)
    diffPlot.setLabels(left='y', bottom='x')
    diffPlot.setRange(xRange=(0, globals.ncol), yRange=(0, globals.nrow))

    QtWidgets.QApplication.instance().exec()
