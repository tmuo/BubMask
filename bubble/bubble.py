"""
Mask R-CNN
Train on the toy Balloon dataset and implement color splash effect.

Copyright (c) 2018 Matterport, Inc.
Licensed under the MIT License (see LICENSE for details)
Written by Waleed Abdulla
------------------------------------------------------------
Modified by Yewon Kim (2022/3)
------------------------------------------------------------

Usage: import the module (see Jupyter notebooks for examples), or run from
       the command line as such:

    # Train a new model starting from pre-trained COCO weights
    python3 bubble.py train --dataset=/path/to/bubble/dataset --weights=coco

    # Resume training a model that you had trained earlier
    python3 bubble.py train --dataset=/path/to/bubble/dataset --weights=last

    # Train a new model starting from ImageNet weights
    python3 bubble.py train --dataset=/path/to/bubble/dataset --weights=imagenet
    
    # Processing masks and bubble information for series of images
    python3 bubble.py detect --weights=/path/to/weights/file.h5 --image=<URL or path to file> --results=/path/to/results
    --folder_num_start=starting folder --folder_num=# of folders --confidence=0.99

    # Apply color splash to an image
    python3 bubble.py splash --weights=/path/to/weights/file.h5 --image=<URL or path to file> 

    & C:/Users/tmuoj/.conda/envs/bubcnn/python.exe C:/Users/tmuoj/OneDrive/Tiedostot/python/aalto/BubMask-1/bubble/bubble.py splash --weights=C:/Users/tmuoj/OneDrive/Tiedostot/python/aalto/BubMask-1/mask_rcnn_bubble.h5 --image=C:/Users/tmuoj/OneDrive/Tiedostot/python/aalto/BubMask/sample_image/1.jpg
"""

import os
import sys
import json
import datetime
import numpy as np
import skimage.draw
from skimage import img_as_uint
from skimage.measure import label, regionprops
import cv2
from imgaug import augmenters as iaa
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
import matplotlib.colors as mcolors
import tensorflow as tf
import datetime
from pathlib import Path

#os.environ["CUDA_VISIBLE_DEVICES"] = "-1" # Comment for GPU

# Root directory of the project
ROOT_DIR = os.path.abspath("")

# Import Mask RCNN
sys.path.append(ROOT_DIR)  # To find local version of the library
from mrcnn.config import Config
from mrcnn import model as modellib, utils

# Path to trained weights file
COCO_WEIGHTS_PATH = os.path.join(ROOT_DIR, "mask_rcnn_coco.h5")
print(f'Trained weights: {COCO_WEIGHTS_PATH}')

# Directory to save logs and model checkpoints, if not provided
# through the command line argument --logs
DEFAULT_LOGS_DIR = os.path.join(ROOT_DIR, "logs/")
Path(os.path.join(DEFAULT_LOGS_DIR)).mkdir(parents=True, exist_ok=True)
print(f'Logs directory: {DEFAULT_LOGS_DIR}')

# Results directory
# Save submission files here
RESULTS_DIR = os.path.join(ROOT_DIR, "results/")
Path(RESULTS_DIR).mkdir(parents=True, exist_ok=True)
print(f'Results directory: {RESULTS_DIR}')

############################################################
#  Configurations
############################################################


class BubbleConfig(Config):
    """Configuration for training on the toy  dataset.
    Derives from the base Config class and overrides some values.
    """
    # Give the configuration a recognizable name
    NAME = "bubble"

    # NUMBER OF GPUs to use. When using only a CPU, this needs to be set to 1.
    GPU_COUNT = 1

    # We use a GPU with 12GB memory, which can fit two images.
    # Adjust down if you use a smaller GPU.
    # Batch size = GPU_COUNT*IMAGES_PER_GPU
    IMAGES_PER_GPU = 1

    # Number of classes (including background)
    NUM_CLASSES = 1 + 1  # Background + bubble

    # Number of training steps per epoch
    STEPS_PER_EPOCH = 5034

    # Number of validation steps to run at the end of every training epoch.
    # A bigger number improves accuracy of validation stats, but slows
    # down the training.
    VALIDATION_STEPS = 32

    # If enabled, resizes instance masks to a smaller size to reduce
    # memory load. Recommended when using high-resolution images.
    USE_MINI_MASK = False
    MINI_MASK_SHAPE = (56, 56)  # (height, width) of the mini-mask
    
    # Backbone network architecture
    # Supported values are: resnet50, resnet101.
    # You can also provide a callable that should have the signature
    # of model.resnet_graph. If you do so, you need to supply a callable
    # to COMPUTE_BACKBONE_SHAPE as well
    BACKBONE = "resnet101"
    
    # Length of square anchor side in pixels
    RPN_ANCHOR_SCALES = (32, 64, 128, 256, 512)

    # Input image resizing
    # Generally, use the "square" resizing mode for training and predicting
    # and it should work well in most cases. In this mode, images are scaled
    # up such that the small side is = IMAGE_MIN_DIM, but ensuring that the
    # scaling doesn't make the long side > IMAGE_MAX_DIM. Then the image is
    # padded with zeros to make it a square so multiple images can be put
    # in one batch.
    # Available resizing modes:
    # none:   No resizing or padding. Return the image unchanged.
    # square: Resize and pad with zeros to get a square image
    #         of size [max_dim, max_dim].
    # pad64:  Pads width and height with zeros to make them multiples of 64.
    #         If IMAGE_MIN_DIM or IMAGE_MIN_SCALE are not None, then it scales
    #         up before padding. IMAGE_MAX_DIM is ignored in this mode.
    #         The multiple of 64 is needed to ensure smooth scaling of feature
    #         maps up and down the 6 levels of the FPN pyramid (2**6=64).
    # crop:   Picks random crops from the image. First, scales the image based
    #         on IMAGE_MIN_DIM and IMAGE_MIN_SCALE, then picks a random crop of
    #         size IMAGE_MIN_DIM x IMAGE_MIN_DIM. Can be used in training only.
    #         IMAGE_MAX_DIM is not used in this mode.
    IMAGE_RESIZE_MODE = "square"
    # Input image resizing
    IMAGE_MIN_DIM = 640 # 640
    IMAGE_MAX_DIM = 640 #1024
    # Minimum scaling ratio. Checked after MIN_IMAGE_DIM and can force further
    # up scaling. For example, if set to 2 then images are scaled up to double
    # the width and height, or more, even if MIN_IMAGE_DIM doesn't require it.
    # However, in 'square' mode, it can be overruled by IMAGE_MAX_DIM.
    IMAGE_MIN_SCALE = None #None
    # Number of color channels per image. RGB = 3, grayscale = 1, RGB-D = 4
    # Changing this requires other changes in the code. See the WIKI for more
    # details: https://github.com/matterport/Mask_RCNN/wiki
    IMAGE_CHANNEL_COUNT = 3
    
    # Image mean (RGB), Average of each channel based on imagenet.
    MEAN_PIXEL = np.array([0, 0, 0])
    
    # How many anchors per image to use for RPN training
    RPN_TRAIN_ANCHORS_PER_IMAGE = 500

    # Non-max suppression threshold to filter RPN proposals.
    # You can increase this during training to generate more propsals.
    RPN_NMS_THRESHOLD = 0.8

    # Number of ROIs per image to feed to classifier/mask heads
    # The Mask RCNN paper uses 512 but often the RPN doesn't generate
    # enough positive proposals to fill this and keep a positive:negative
    # ratio of 1:3. You can increase the number of proposals by adjusting
    # the RPN NMS threshold.
    TRAIN_ROIS_PER_IMAGE = 300

    # Maximum number of ground truth instances to use in one image
    MAX_GT_INSTANCES = 200

    # Max number of final detections
    DETECTION_MAX_INSTANCES = 300

    # Shape of output mask
    # To change this you also need to change the neural network mask branch
    MASK_SHAPE = [56, 56]

    # Weight decay regularization
    WEIGHT_DECAY = 0.0001

    # Loss weights for more precise optimization.
    # Can be used for R-CNN training setup.
    LOSS_WEIGHTS = {
        "rpn_class_loss": 1.,
        "rpn_bbox_loss": 1.,
        "mrcnn_class_loss": 1.,
        "mrcnn_bbox_loss": 1.,
        "mrcnn_mask_loss": 1.

    }
    
    # Skip detections with < 60% confidence
    DETECTION_MIN_CONFIDENCE = 0.6
    
    # Bubble mean size to normalize weight
    MEAN_SIZE = 47.0
    MIN_SIZE = 1e-4
    MAX_SIZE = 155.3
    WEIGHT_WIDTH = 3
    
class BubbleInferenceConfig(BubbleConfig):
    # Set batch size to 1 to run one image at a time
    GPU_COUNT = 1
    IMAGES_PER_GPU = 1
    # Don't resize imager for inferencing
    IMAGE_RESIZE_MODE = "pad64"
    IMAGE_MIN_DIM = 320
    # Non-max suppression threshold to filter RPN proposals.
    # You can increase this during training to generate more propsals.
    RPN_NMS_THRESHOLD = 0.8
    DETECTION_MIN_CONFIDENCE = 0.5
    
class _InfConfig(BubbleConfig):
    IMAGES_PER_GPU = 1
    GPU_COUNT = 1
    IMAGE_RESIZE_MODE = "pad64"
    IMAGE_MIN_DIM = 320
    
############################################################
#  Dataset
############################################################

class BubbleDataset(utils.Dataset):

    def load_bubble(self, dataset_dir, subset):
        """Load a subset of the Bubble dataset.
        dataset_dir: Root directory of the dataset.
        subset: Subset to load: train or val
        """
        # Add classes. We have only one class to add.
        self.add_class("bubble", 1, "bubble")

        # Train or validation dataset?
        assert subset in ["train", "val"]
        dataset_dir = os.path.join(dataset_dir, subset)

        # Get image ids from directory names
        image_ids = next(os.walk(dataset_dir))[1]
        image_ids = list(set(image_ids))

        # Add images
        for image_id in image_ids:
            self.add_image(
                "bubble",
                image_id=image_id,
                path=os.path.join(dataset_dir, image_id, "images", "{}.jpg".format(image_id)))

    def load_mask(self, image_id):
        """Generate instance masks for an image.
       Returns:
        masks: A bool array of shape [height, width, instance count] with
            one mask per instance.
        class_ids: a 1D array of class IDs of the instance masks.
        """
        info = self.image_info[image_id]
        # Get mask directory from image path
        mask_dir = os.path.join(os.path.dirname(os.path.dirname(info['path'])), "masks")

        # Read mask files from .png image
        mask = []
        for f in next(os.walk(mask_dir))[2]:
            if f.endswith(".png"):
                m = skimage.io.imread(os.path.join(mask_dir, f)).astype(np.bool)
                mask.append(m)
        mask = np.stack(mask, axis=-1)
        # Return mask, and array of class IDs of each instance. Since we have
        # one class ID, we return an array of ones
        return mask, np.ones([mask.shape[-1]], dtype=np.int32)

    def image_reference(self, image_id):
        """Return the path of the image."""
        info = self.image_info[image_id]
        if info["source"] == "bubble":
            return info["path"]
        else:
            super(self.__class__, self).image_reference(image_id)


def train(model):
    """Train the model."""
    # Training dataset.
    dataset_train = BubbleDataset()
    dataset_train.load_bubble(args.dataset, "train")
    dataset_train.prepare()

    # Validation dataset
    dataset_val = BubbleDataset()
    dataset_val.load_bubble(args.dataset, "val")
    dataset_val.prepare()
    
    model_inference = modellib.MaskRCNN(mode="inference", config=_InfConfig(), model_dir=args.logs)
    mean_average_precision_callback = modellib.MeanAveragePrecisionCallback(model, model_inference, dataset_val, 1, 32,
                                                                        verbose=1)
    
    # Image augmentation
    # http://imgaug.readthedocs.io/en/latest/source/augmenters.html
    augmentation = iaa.SomeOf((0, 10), [
        iaa.Fliplr(0.5),
        iaa.Flipud(0.5),
        iaa.Add((-40, 40)),
        iaa.AdditiveGaussianNoise(scale=(0, 0.2*255)),
        iaa.Multiply((0.25, 1)),
        iaa.MedianBlur(k=(3, 15)),
        iaa.SigmoidContrast(gain=(5, 10), cutoff=(0.1, 0.6)),
        iaa.Sharpen(alpha=(0.0, 1.0), lightness=(0.75, 1.1)),
        iaa.Affine(scale={"x": (0.5, 2), "y": (0.1, 1.5)}), #(0.2,0.6)
        iaa.Affine(shear=(-40, 40)),
        iaa.PiecewiseAffine(scale=(0.01, 0.06)),
        iaa.OneOf([iaa.Affine(rotate=90),
                   iaa.Affine(rotate=180),
                   iaa.Affine(rotate=270)])

    ])

    # *** This training schedule is an example. Update to your needs ***
    # Since we're using a very small dataset, and starting from
    # COCO trained weights, we don't need to train too long. Also,
    # no need to train all layers, just the heads should do it.
    
    model.train(dataset_train, dataset_val,
                learning_rate=config.LEARNING_RATE/10,
                epochs=10,
                augmentation=augmentation,
               layers='5+',
                custom_callbacks=[mean_average_precision_callback])
    
    model.train(dataset_train, dataset_val,
                learning_rate=config.LEARNING_RATE/100,
                epochs=20,
                augmentation=augmentation,
                layers='5+',
                custom_callbacks=[mean_average_precision_callback])
    
    model.train(dataset_train, dataset_val,
                learning_rate=config.LEARNING_RATE/1000,
                epochs=30,
                augmentation=augmentation,
                layers='5+',
                custom_callbacks=[mean_average_precision_callback])
    
    
def color_splash(image, mask):
    """Apply color splash effect.
    image: RGB image [height, width, 3]
    mask: instance segmentation mask [height, width, instance count]
    Returns result image.
    """
    # Make a grayscale copy of the image. The grayscale copy still
    # has 3 RGB channels, though.
    gray = skimage.color.gray2rgb(skimage.color.rgb2gray(image)) * 255
    image = image*np.array([255/255,0/255,255/255])+75
    image = np.where(image>255, 255, image).astype(np.uint8)
    # Copy color pixels from the original color image where mask is set
    if mask.shape[-1] > 0:
        # We're treating all instances as one, so collapse the mask into one layer
        mask = (np.sum(mask, -1, keepdims=True) >= 1)
        splash = np.where(mask, image, gray).astype(np.uint8)
    else:
        splash = gray.astype(np.uint8)
    return splash
    

def detect(model, image_path=None, result_path=RESULTS_DIR):
    """Processing PNG masks and bubble information txt file for series of images
    """
    assert image_path

    # Create directory
    if not os.path.exists(result_path):
        os.makedirs(result_path)     
    
    for FN in range(int(args.folder_num_start), int(args.folder_num_start)+int(args.folder_num)):
        IMAGE_PATH = args.image + "_%03i"%(FN+1) 
        print("Running on {}".format(IMAGE_PATH))
        # Create results directory
        IMAGE_PATH_results = os.path.join(result_path, os.path.basename(IMAGE_PATH)) 
        if not os.path.exists(IMAGE_PATH_results):
            os.makedirs(IMAGE_PATH_results)   
        
        # Image list for current folder
        files = os.listdir(IMAGE_PATH)
        
        for file in files:
            # make sure file is an image
            if file.endswith(('.jpg', '.png', '.tif')): 
                img_path = os.path.join(IMAGE_PATH, file)
         
                # Read image
                image = skimage.io.imread(img_path)
        
                # 3 channel jpg?? 
                if image.ndim == 2:
                    image = cv2.merge((image,image,image))
        
                # Detect objects
                a = datetime.datetime.now()
                r = model.detect([image], verbose=1)[0]
                b = datetime.datetime.now()
                c = b-a
                print('detection time = ', c.total_seconds())
        
                # Create results directory
                img_path_results = os.path.join(IMAGE_PATH_results, file.rsplit('.')[0])
                if not os.path.exists(img_path_results):
                    os.makedirs(img_path_results)
                
                # Save PNG masks & calculating bubble information
                props_list = [["x ", "y ", "Orientation ", "Axis_major_length ", "Axis_minor_length ", "Area "]]
                
                for png_num in range(r['masks'].shape[2]):
                    file_name = "mask_%03i.png"%(png_num+1)
                    skimage.io.imsave(os.path.join(img_path_results, file_name), img_as_uint(r['masks'][:,:,png_num])) 
        
                    # Caculate bubble information & save as txt
                    label_img = label(r['masks'][:,:,png_num])
                    props = regionprops(label_img)
                    props_list.append([round(props[0].centroid[1],2), round(props[0].centroid[0],2), round(props[0].orientation,2),
                                                          round(props[0].major_axis_length,2), round(props[0].minor_axis_length,2), 
                                                          round(props[0].area,2)])
				# Save PNG mask for all bubbles
                if args.all_bubble_mask:
                    skimage.io.imsave(os.path.join(IMAGE_PATH_results, file.rsplit('.')[0] + ".png"), np.sum(r['masks'],axis=2))
            
                with open(os.path.join(img_path_results, file.rsplit('.')[0] + ".txt"), "w") as file2:
                    for line in props_list:
                        file2.write("%s\n" % str(line)[1 : -1])
      
                print("Saved to ", os.path.join(img_path_results, file.rsplit('.')[0], ".txt"))
    

def splash(model, image_path=None, video_path=None, result_path=RESULTS_DIR):
    assert image_path or video_path

    # Create directory
    if not os.path.exists(result_path):
        os.makedirs(result_path)
        
    # Custom color map
    colors1 = plt.cm.Blues(np.linspace(0.05, 0.05, 1))
    colors2 = plt.cm.Blues(np.linspace(0.25, 0.75, 128))
    
    # combine them and build a new colormap
    colors = np.vstack((colors1, colors2))
    mymap = mcolors.LinearSegmentedColormap.from_list('my_colormap', colors)

    # Image or video?
    if image_path:
        # Run model detection and generate the color splash effect
        print("Running on {}".format(args.image))
        # Read image
        image = skimage.io.imread(args.image)
        # 3 channel jpg?? 
        if image.ndim == 2:
            image = cv2.merge((image,image,image))
        # Detect objects
        a = datetime.datetime.now()
        r = model.detect([image], verbose=1)[0]
        b = datetime.datetime.now()
        c = b-a
        print('detection time = ', c.total_seconds())
        # Color splash
        splash = color_splash(image, r['masks'])
        # Save output
        file_name = "splash_"+os.path.basename(args.image).rsplit('.')[0]+".png"
        skimage.io.imsave(os.path.join(result_path, file_name), splash)
    elif video_path:
        # Video capture
        vcapture = cv2.VideoCapture(video_path)
        width = int(vcapture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(vcapture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = 30

        # Define codec and create video writer
        file_name = "splash_"+os.path.basename(video_path).rsplit('.')[0]+".wmv"
        vwriter = cv2.VideoWriter(os.path.join(result_path, file_name),
                                  cv2.VideoWriter_fourcc(*'MJPG'),
                                  fps, (width, height))

        count = 0
        success = True
        while success:
            print("frame: ", count)
            # Read next image
            success, image = vcapture.read()
            if success:
                # OpenCV returns images as BGR, convert to RGB
                image = image[..., ::-1]
                # 3 channel jpg?? 
                if image.ndim == 2:
                    image = cv2.merge((image,image,image))
                # Detect objects
                a = datetime.datetime.now()
                r = model.detect([image], verbose=0)[0]
                b = datetime.datetime.now()
                c = b-a
                print('detection time = ', c.total_seconds())
                # Color splash
                splash = color_splash(image, r['masks'])
                # RGB -> BGR to save image to video
                splash = splash[..., ::-1]
                # Add image to video writer
                vwriter.write(splash)
                count += 1
        vwriter.release()
    print("Saved to ", os.path.join(result_path, file_name))


############################################################
#  Training
############################################################

if __name__ == '__main__':
    import argparse

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Train Mask R-CNN to detect bubbles.')
    parser.add_argument("--command",
                        metavar="<command>",
                        default='splash',
                        help="'train' or 'splash' or 'detect'")
    parser.add_argument('--dataset', required=False,
                        metavar="/path/to/bubble/dataset/",
                        default='C:/Users/tmuoj/OneDrive/Tiedostot/python/aalto/BubMask-1/dataset_RGB/',
                        help='Directory of the Bubble dataset')
    parser.add_argument('--weights', required=False,
                        metavar="/path/to/weights.h5",
                        default='C:/Users/tmuoj/OneDrive/Tiedostot/python/aalto/BubMask-1/mask_rcnn_bubble.h5',
                        help="Path to weights .h5 file or 'coco'")
    parser.add_argument('--logs', required=False,
                        default=DEFAULT_LOGS_DIR,
                        metavar="/path/to/logs/",
                        help='Logs and checkpoints directory (default=logs/)')
    parser.add_argument('--results', required=False,
                        default=RESULTS_DIR,
                        metavar="/path/to/results/",
                        help='Save submission files here (default=resuls/bubble)')
    parser.add_argument('--image', required=False,
                        metavar="path or URL to image",
                        default='C:/Users/tmuoj/OneDrive/Tiedostot/python/aalto/BubMask-1/sample_image/Expansion_pipe.jpg',
                        help='Image to apply the color splash effect on')
    parser.add_argument('--video', required=False,
                        metavar="path or URL to video",
                        help='Video to apply the color splash effect on')
    parser.add_argument('--folder_num', required=False,
                        default=1,
                        metavar="number of folders (default=1)",
                        help='Number of total folders to detect')
    parser.add_argument('--folder_num_start', required=False,
                        default=0,
                        metavar="starting folders",
                        help='Where to start detecting (default=0)')
    parser.add_argument('--all_bubble_mask', required=False,
                        default=0,
                        metavar="Entire bubble mask",
                        help='If need entire bubble mask (default=0)')
    parser.add_argument('--confidence', required=False,
                        default=0.99,
                        metavar="0.5~0.99",
                        help='Skip detections with < confidence (default=0.99)')
    args = parser.parse_args()

    # Validate arguments
    if args.command == "train":
        assert args.dataset, "Argument --dataset is required for training"
    elif args.command == "splash":
        assert args.image or args.video,\
               "Provide --image or --video to apply color splash"

    print("Weights: ", args.weights)
    print("Dataset: ", args.dataset)
    print("Logs: ", args.logs)
    print("Results: ", args.results)

    # Configurations
    if args.command == "train":
        config = BubbleConfig()
    else:
        class InferenceConfig(BubbleConfig):
            # Set batch size to 1 since we'll be running inference on
            # one image at a time. Batch size = GPU_COUNT * IMAGES_PER_GPU
            GPU_COUNT = 1
            IMAGES_PER_GPU = 1
            # Don't resize imager for inferencing
            IMAGE_RESIZE_MODE = "pad64"
            IMAGE_MIN_DIM = 320 #640 1024
            # Non-max suppression threshold to filter RPN proposals.
            # You can increase this during training to generate more propsals.
            RPN_NMS_THRESHOLD = 0.8 #0.8~0.98
            
            # Skip detections with < 60% confidence
            DETECTION_MIN_CONFIDENCE = float(args.confidence) # 0.5~0.99
        config = InferenceConfig()
    config.display()

    # Create model
    if args.command == "train":
        model = modellib.MaskRCNN(mode="training", config=config,
                                  model_dir=args.logs)
    else:
        model = modellib.MaskRCNN(mode="inference", config=config,
                                  model_dir=args.logs)

    # Select weights file to load
    if args.weights.lower() == "coco":
        weights_path = COCO_WEIGHTS_PATH
        # Download weights file
        if not os.path.exists(weights_path):
            utils.download_trained_weights(weights_path)
    elif args.weights.lower() == "last":
        # Find last trained weights
        weights_path = model.find_last()
    elif args.weights.lower() == "imagenet":
        # Start from ImageNet trained weights
        weights_path = model.get_imagenet_weights()
    else:
        weights_path = args.weights

    # Load weights
    print("Loading weights ", weights_path)
    if args.weights.lower() == "coco":
        # Exclude the last layers because they require a matching
        # number of classes
        model.load_weights(weights_path, by_name=True, exclude=[
            "mrcnn_class_logits", "mrcnn_bbox_fc",
            "mrcnn_bbox", "mrcnn_mask"])
    else:
        model.load_weights(weights_path, by_name=True)

    # Train or evaluate
    if args.command == "train":
        train(model)
    elif args.command == "splash":
        splash(model, image_path=args.image,
                                video_path=args.video, result_path=args.results)
    elif args.command == "detect":
        detect(model, image_path=args.image, result_path=args.results)
    
    else:
        print("'{}' is not recognized. "
              "Use 'train' or 'splash' or 'detect'".format(args.command))
