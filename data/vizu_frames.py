import numpy as np
import matplotlib.pyplot as plt

# Load the .npz file
loaded_data = np.load('frames_for_fitting.npz')
keys = list(loaded_data.files)

fig, ax = plt.subplots()
plt.subplots_adjust(bottom=0.2)

def plot_array():
    ax.clear()  # Clear the axes to prevent overlap

    array = loaded_data[keys[index]]
    if array.ndim == 2:
        ax.imshow(array, aspect='auto', cmap='viridis', origin='lower')
    else:
        ax.plot(array, label=f'Array for key {keys[index]}')
        ax.legend()

    ax.set_title(f'Visualization of frame -> {keys[index]}')
    ax.set_xlabel('Index')
    ax.set_ylabel('Value')
    fig.canvas.draw()

# Initial plot
index = 0
plot_array()

# Update function
def update_plot(event):
    global index

    if event.key == 'right':
        index = (index + 1) % len(keys)
    elif event.key == 'left':
        index = (index - 1) % len(keys)

    plot_array()

# Connect the update function to key press events
fig.canvas.mpl_connect('key_press_event', update_plot)

plt.show()
