from torch.utils.data import Dataset, DataLoader
from PIL import Image
import torch
import os
import torchvision.transforms as transforms
import torch.nn.functional as F
import cv2
import matplotlib.pyplot as plt
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch
import torch.nn as nn
import torch.nn.functional as F
from pytorch_msssim import ssim, ms_ssim
import matplotlib.pyplot as plt
import torch
import numpy as np
import cv2
from tqdm import tqdm

class FusionDataset:
    def __init__(self, basedir, size, transform=None, levels=None):
        self.transform = transforms.Compose([transforms.Resize(size), transforms.ToTensor()])
        self.image_groups = []
        self.size = size
        self.levels = levels

        for p in os.listdir(basedir):
            level_dir = os.path.join(basedir, p)
            if not os.path.isdir(level_dir):
                continue

            for patient in os.listdir(level_dir):
                patient_dir = os.path.join(level_dir, patient)
                level_0_dir = os.path.join(patient_dir, "FusedImages_Level_0")

                if not os.path.exists(level_0_dir):
                    continue

                if levels is None:
                    num_levels = sum(1 for d in os.listdir(patient_dir) if d.startswith("FusedImages_Level_"))
                else:
                    num_levels = levels

                print(f"Processing patient {patient} in {p} with {num_levels} levels")

                for base_idx in range(len(os.listdir(level_0_dir))):
                    paths = []
                    names = []
                    current_idx = base_idx
                    valid_group = True

                    # Level 0
                    name = f"Fused_Image_Level_0_{base_idx}.tif"
                    path = os.path.join(level_0_dir, name)

                    if not os.path.exists(path):
                        continue

                    paths.append(path)
                    names.append(name)

                    for level in range(1, num_levels):
                        current_idx = current_idx // 2
                        name = f"Fused_Image_Level_{level}_{current_idx}.tif"
                        path = os.path.join(patient_dir, f"FusedImages_Level_{level}", name)

                        if not os.path.exists(path):
                            valid_group = False
                            break

                        paths.append(path)
                        names.append(name)

                    if valid_group:
                        self.image_groups.append((paths, names))

    def _apply_transform(self, img):
        img = Image.fromarray(img) 
        img = self.transform(img)   
        return img
    
    def __len__(self):
        return len(self.image_groups)
    
    def __getitem__(self, idx):
        paths, names = self.image_groups[idx]
        images = []
        
        for path in paths:
            img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if img is None:
                raise ValueError(f"Failed to load image: {path}")
                
            img = self._apply_transform(img)
            images.append(img)
        
        stacked_images = torch.stack(images)
        
        return [stacked_images, names] 

def get_dataset(basedir = "../FusedDataset", size=512, levels=None):

    dataset = FusionDataset(basedir=basedir, size=size, levels=levels)

    train_set, val_set = torch.utils.data.random_split(dataset, [int(len(dataset)*0.90), int(len(dataset)*0.1)+1])
    val_size = len(val_set)
    split_size = val_size // 2
    remainder = val_size % 2
    val_split = split_size + remainder  # Add remainder to one split
    test_split = split_size
    #val_set, test_set = torch.utils.data.random_split(val_set, [round(int(len(val_set)*0.50)), round(int(len(val_set)*0.50))+1])
    val_set, test_set = torch.utils.data.random_split(val_set, [val_split, test_split])


    train_loader = DataLoader(train_set, batch_size=1, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=1, shuffle=False)
    test_loader = DataLoader(test_set, batch_size=1, shuffle=False)

    return train_loader, val_loader, test_loader