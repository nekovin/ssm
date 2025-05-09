import os
import glob
import numpy as np
import cv2
from skimage import io
import matplotlib.pyplot as plt
import torch
from torch.utils.data import Dataset, DataLoader
import numpy as np

def normalize_image(np_img):
    if np_img.max() > 0:
        # Create mask of non-background pixels
        foreground_mask = np_img > 0.01
        if foreground_mask.any():
            # Get min/max of only foreground pixels
            fg_min = np_img[foreground_mask].min()
            fg_max = np_img[foreground_mask].max()
            
            # Normalize only foreground pixels to [0,1] range
            if fg_max > fg_min:
                np_img[foreground_mask] = (np_img[foreground_mask] - fg_min) / (fg_max - fg_min)
    
    # Force background to be true black
    np_img[np_img < 0.01] = 0
    return np_img

def load_patient_data(base_path, verbose=False):
    """
    Load OCT B-scans for a patient from the specified path.
    
    Args:
        base_path: Path to the directory containing the OCT images
        
    Returns:
        List of loaded OCT scans as normalized numpy arrays
    """
    if verbose:
        print(f"Loading data from: {base_path}")
    
    # Find all TIFF files in the directory
    files = sorted(glob.glob(os.path.join(base_path, "*.tiff")))
    if not files:
        # Try other possible extensions if no .tiff files are found
        files = sorted(glob.glob(os.path.join(base_path, "*.tif")))
    if not files:
        files = sorted(glob.glob(os.path.join(base_path, "*.png")))
    if not files:
        files = sorted(glob.glob(os.path.join(base_path, "*.jpg")))
    
    if verbose:
        print(f"Found {len(files)} files")
    
    # Load and preprocess images
    oct_scans = []
    for file in files:
        try:
            # Read the image
            img = io.imread(file)
            
            # Convert to float32 and normalize to [0, 1]
            img = img.astype(np.float32)
            if img.max() > 1.0:
                img = img / 255.0
                
            oct_scans.append(img)
        except Exception as e:
            print(f"Error loading {file}: {e}")
    
    return oct_scans


def standard_preprocessing(oct_volume):
    preprocessed = []
    #print(oct_volume[0].shape)
    for img in oct_volume:
        if img.max() > 1.0:
            img = img / 255.0
        
        # Add channel dimension if needed
        if len(img.shape) == 2:
            img_with_channel = img.reshape(*img.shape, 1)
        else:
            img_with_channel = img
        resized = cv2.resize(img_with_channel, (256, 256), interpolation=cv2.INTER_LINEAR)
        preprocessed.append(resized)

    #print(f"Preprocessed shape: {preprocessed[0].shape}")

    return np.array(preprocessed)

def standard_preprocessing(oct_volume):
    preprocessed = []
    #print(f"Number of images: {len(oct_volume)}")
    #print(f"First image shape: {oct_volume[0].shape}")
    
    for i, img in enumerate(oct_volume):
        #print(f"Image {i} - Original shape: {img.shape}, dtype: {img.dtype}")
        
        if img.max() > 1.0:
            img = img / 255.0
        
        # Force 2D image (handle any dimensionality issues)
        if len(img.shape) > 2:
            img = img[:, :, 0]  # Take first channel
        
        # Resize consistently
        resized = cv2.resize(img, (256, 256), interpolation=cv2.INTER_LINEAR)
        
        # Explicitly add channel dimension
        resized = resized[:, :, np.newaxis]
        
        #print(f"Image {i} - Resized shape: {resized.shape}")
        preprocessed.append(resized)

    return np.array(preprocessed)

def octa_preprocessing(preprocessed_data, n_neighbours=1, threshold=20):
    """
    Calculate OCTA images using multiple neighboring B-scans
    
    Args:
        preprocessed_data: List of OCT B-scans
        n_neighbours: Number of neighbors to consider on each side for OCTA calculation
        threshold: Percentile threshold for background masking
        
    Returns:
        List of OCTA images
    """
    n_scans = len(preprocessed_data)
    octa_images = []
    
    # For each scan position (except the edges where we don't have enough neighbors)
    for i in range(n_neighbours, n_scans - n_neighbours):
        # Collect all decorrelation values from comparing the center scan with its neighbors
        decorrelation_values = []
        center_scan = preprocessed_data[i]
        
        # Compare with previous n_neighbours scans
        for j in range(i-n_neighbours, i):
            neighbor_scan = preprocessed_data[j]
            decorr = compute_decorrelation(center_scan, neighbor_scan)
            decorrelation_values.append(decorr)
            
        # Compare with next n_neighbours scans
        for j in range(i+1, i+n_neighbours+1):
            neighbor_scan = preprocessed_data[j]
            decorr = compute_decorrelation(center_scan, neighbor_scan)
            decorrelation_values.append(decorr)
        
        # Average all decorrelation values to get final OCTA
        if decorrelation_values:
            avg_decorrelation = np.mean(np.stack(decorrelation_values), axis=0)
            thresholded_octa = threshold_octa(avg_decorrelation, center_scan, threshold)
            octa_images.append(thresholded_octa)
    
    return octa_images

def compute_decorrelation(oct1, oct2):

    numerator = (oct1 - oct2)**2
    denominator = oct1**2 + oct2**2
    
    epsilon = 1e-6  # Small constant to avoid division by zero
    decorrelation = numerator / (denominator + epsilon)
    
    return decorrelation

from skimage.filters import threshold_local
def threshold_octa(octa, oct, threshold):

    # Create mask based on OCT intensity
    background_mask = oct < np.percentile(oct, threshold)  # Bottom percentage as background
    
    if np.sum(background_mask) > 0:  # Ensure we have background pixels
        background_mean = np.mean(oct[background_mask])
        background_std = np.std(oct[background_mask])
        
        intensity_threshold = background_mean + 2 * background_std
    else:
        # If no background pixels, use a fixed threshold
        #print("No background pixels found, using fixed threshold")
        intensity_threshold = np.percentile(oct, threshold)
    
    # Create mask for significant signal
    #signal_mask = oct > intensity_threshold

    signal_mask = np.clip((oct - intensity_threshold) / (background_std * 2), 0, 1)

    #plt.imshow(octa, cmap='gray')
    #plt.show()
    
    # Apply mask to OCTA
    thresholded_octa = octa * signal_mask
    
    return thresholded_octa

def pair_data(preprocessed_data, octa_data, n_images_per_patient):
    preprocessed_data = preprocessed_data[:-1]  # Remove last scan to avoid out of bounds

    input_target = []
    j = 0
    for p, o in zip(preprocessed_data, octa_data):
        input_target.append([p, o])
        j += 1
        if j >= n_images_per_patient:
            break

    return input_target

def pair_data(preprocessed_data, octa_data, n_images_per_patient):
    # Calculate the offset due to n_neighbours
    n_neighbours = (len(preprocessed_data) - len(octa_data)) // 2
    
    input_target = []
    for i in range(len(octa_data)):
        # Match each octa image with its corresponding OCT image
        # The octa at index i corresponds to the preprocessed at index i+n_neighbours
        oct_image = preprocessed_data[i + n_neighbours]
        octa_image = octa_data[i]
        input_target.append([oct_image, octa_image])
        
        if len(input_target) >= n_images_per_patient:
            break
            
    return input_target

def remove_speckle_noise(image, min_size=5):
    """
    Remove small isolated speckles from an OCTA image
    
    Args:
        image: Input image (2D numpy array)
        min_size: Minimum size of regions to keep (in pixels)
        
    Returns:
        Cleaned image with small isolated speckles removed
    """
    import cv2
    import numpy as np
    
    # Ensure we're working with a 2D image
    if len(image.shape) > 2:
        if image.shape[2] == 1:
            image_2d = image[:,:,0]
        else:
            # Convert multi-channel to grayscale
            image_2d = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        image_2d = image
    
    # Create binary image
    binary = (image_2d > 0).astype(np.uint8)
    
    # Find connected components
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    
    # Create mask, keeping only components larger than min_size
    mask = np.zeros_like(binary)
    for i in range(1, num_labels):  # Skip background (0)
        if stats[i, cv2.CC_STAT_AREA] >= min_size:
            mask[labels == i] = 1
    
    # Apply mask to original image
    if len(image.shape) > 2:
        # For multi-channel images
        for c in range(image.shape[2]):
            image[:,:,c] = image[:,:,c] * mask
    else:
        # For single-channel images
        image = image * mask
    
    return image

def preprocessing_v2(start=1, n_patients=1, n_images_per_patient=10, n_neighbours=2, threshold=0.65, sample = False, post_process_size=10):
    
    dataset = {}
    try:
        for i in range(start, start+n_patients):
            data = load_patient_data(rf"C:\Datasets\ICIP training data\ICIP training data\0\RawDataQA ({i})")
            assert len(data) > 0, f"No data found for patient {i}"
            
            preprocessed_data = standard_preprocessing(data)

            

            octa_data = octa_preprocessing(preprocessed_data, n_neighbours, threshold)
            
            cleaned_octa_data = []
            for octa_img in octa_data:
                cleaned_img = remove_speckle_noise(octa_img, min_size=post_process_size)
                cleaned_octa_data.append(cleaned_img)
            
            input_target_data = pair_data(preprocessed_data, cleaned_octa_data, n_images_per_patient)
            
            dataset[i] = input_target_data
            
        return dataset
    
    except Exception as e:
        print(f"Error in preprocessing: {e}")
        return None


class OCTDataset(Dataset):
    def __init__(self, start, n_patients=2, n_images_per_patient=50, transform=None):
        """
        Dataset class for OCT images
        
        Args:
            n_patients: Number of patients to include
            n_images_per_patient: Maximum number of images per patient
            transform: Optional transforms to apply
        """
        self.transform = transform
        
        # Process OCT data
        dataset_dict = preprocessing_v2(start, n_patients, n_images_per_patient, n_neighbours=2)
        
        # Store image pairs
        self.input_images = []
        self.target_images = []
        
        for patient_id, data in dataset_dict.items():
            print(f"Processing patient {patient_id} with {len(data)} images")
            for i in range(len(data) - 1):  # Use consecutive pairs
                input_image = data[i][0]  # First scan as input
                target_image = data[i+1][0]  # Next scan as target
                
                # Handle potential NaN or Inf values
                if np.isfinite(input_image).all() and np.isfinite(target_image).all():
                    self.input_images.append(input_image)
                    self.target_images.append(target_image)
    
    def __len__(self):
        return len(self.input_images)
    
    def __getitem__(self, idx):
        input_img = self.input_images[idx]
        target_img = self.target_images[idx]
        
        # Add channel dimension if needed
        if len(input_img.shape) == 2:
            input_img = input_img[:, :, np.newaxis]
            target_img = target_img[:, :, np.newaxis]
        
        # Convert to PyTorch tensors
        input_tensor = torch.from_numpy(input_img.transpose(2, 0, 1)).float()
        target_tensor = torch.from_numpy(target_img.transpose(2, 0, 1)).float()
        
        # Apply transformations if any
        if self.transform:
            input_tensor = self.transform(input_tensor)
            target_tensor = self.transform(target_tensor)
            
        return input_tensor, target_tensor

def get_loaders(start, n_patients=2, n_images_per_patient=50, batch_size=8, 
                val_split=0.2, shuffle=True, random_seed=42):

    full_dataset = OCTDataset(start, n_patients=n_patients, n_images_per_patient=n_images_per_patient)
    
    dataset_size = len(full_dataset)
    print(f"Dataset size: {dataset_size}")
    val_size = int(val_split * dataset_size)
    train_size = dataset_size - val_size
    
    random = False
    if random:
        train_dataset, val_dataset = torch.utils.data.random_split(
            full_dataset, 
            [train_size, val_size],
            generator=torch.Generator().manual_seed(random_seed)
        )
    else:
        train_dataset = torch.utils.data.Subset(
            full_dataset, 
            np.arange(train_size)
        )

        val_dataset = torch.utils.data.Subset(
            full_dataset, 
            np.arange(train_size, dataset_size)
        )
    
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size, 
        shuffle=shuffle, 
        num_workers=0
    )
    
    val_loader = DataLoader(
        val_dataset, 
        batch_size=batch_size, 
        shuffle=False, 
        num_workers=0
    )
    
    return train_loader, val_loader

def get_train_loaders(start, n_patients=2, n_images_per_patient=50, batch_size=8, 
                val_split=0.2, shuffle=True, random_seed=42):

    full_dataset = OCTDataset(start, n_patients=n_patients, n_images_per_patient=n_images_per_patient)
    
    dataset_size = len(full_dataset)
    val_size = int(val_split * dataset_size)
    train_size = dataset_size - val_size
    
    train_dataset, val_dataset = torch.utils.data.random_split(
        full_dataset, 
        [train_size, val_size],
        generator=torch.Generator().manual_seed(random_seed)
    )
    
    train_loader = DataLoader(
        train_dataset, 
        batch_size=batch_size, 
        shuffle=shuffle, 
        num_workers=0
    )
    
    val_loader = DataLoader(
        val_dataset, 
        batch_size=batch_size, 
        shuffle=False, 
        num_workers=0
    )
    
    return train_loader, val_loader