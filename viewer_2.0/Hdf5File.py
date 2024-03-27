import hdf5plugin
import h5py
from pathlib import Path
import numpy as np
import functools


def string_dt(s):
    tid = h5py.h5t.C_S1.copy()
    tid.set_size(len(s))
    return h5py.Datatype(tid)

def create_string_attr(obj, key, value):
    #Albula requires null terminated strings
    if value[-1] != "\x00":
        value += "\x00"
    obj.attrs.create(key, value, dtype=string_dt(value))


def check_read(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            print(f'calling: {func.__name__} with: {self.mode}')
            if 'r' not in self.mode:
                raise ValueError(f"File not open for reading")
            return func(self, *args, **kwargs)

        return wrapper

def check_write(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if 'w' not in self.mode:
                raise ValueError(f"File not open for writing")
            return func(self, *args, **kwargs)

        return wrapper


class Hdf5File:
    def __init__(self, filename, mode='r', image_size = (512,1024), dtype = np.float32, pixel_mask = None):
        filename = Path(filename)
        self.filename = filename
        self.mode = mode

        #shape and data type only matters for writing
        self._image_size = image_size 
        self.dt = dtype
        self.frame_index = 0

        #for writing if the folder does not exist, create it
        if self.mode == 'w':
            path = filename.parent
            path.mkdir(exist_ok=True)
            self.file = h5py.File(self.filename, self.mode)

            compression=hdf5plugin.Bitshuffle(nelems=0, cname='lz4')
            nxentry = self.file.create_group("entry")
            create_string_attr(nxentry, "NX_class", "NXentry")
            nxdata = nxentry.create_group("data")
            create_string_attr(nxdata, "NX_class", "NXdata")
            self.ds = nxdata.create_dataset(
                "data_000001",
                shape=(0,*self._image_size),
                dtype=self.dt,
                maxshape=(None, *self._image_size),
                chunks = (1, *self._image_size),
                **compression,
            )
            self.ds.attrs["image_nr_low"] = np.int32(0)

            #Pixel mask for albula, respected by other applications? 
            if pixel_mask is None:
                pixel_mask = np.zeros(self._image_size, dtype = np.uint8) 
            inst = nxentry.create_group("instrument/detector/detectorSpecific")
            inst.create_dataset("pixel_mask", data=pixel_mask.astype(np.uint8), **compression)
            
            

        elif self.mode == 'r':
            self.file = h5py.File(self.filename, self.mode)
            #TODO! Add checks for the file structure

        else:
            raise ValueError(f"Mode {self.mode} not recognized")
    @property    
    def image_size(self):
        return self.file['entry/data/data_000001'].shape[1:]   

    @property
    def n_frames(self):
        return self.file['entry/data/data_000001'].shape[0]

    @check_write
    def write(self, image):
        if image.shape != self._image_size:
            raise ValueError(f"Image shape {image.shape} does not match expected shape {self.shape}")
        
        self.ds.resize(self.frame_index + 1, axis = 0)
        self.ds[self.frame_index] = image
        self.ds.attrs["image_nr_high"] = np.int32(self.n_frames - 1)
        self.frame_index += 1
    
    @check_read
    def read(self):
        if self.frame_index < self.n_frames:
            data = self.file['entry/data/data_000001'][self.frame_index]
            self.frame_index += 1
            return data
        else:
            raise EOFError("End of file reached")

    
    def tell(self):
        return self.frame_index

    def seek(self, frame_number):
        self.frame_index = frame_number

    def close(self):
        self.file.close()

