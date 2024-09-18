import numpy as np

# Load the .npz file
data = np.load('frames_for_fitting.npz')

# Iterate over the keys and print the shape of each array
for key in data.files:
    print(f"Array '{key}' has shape: {data[key].shape}")
