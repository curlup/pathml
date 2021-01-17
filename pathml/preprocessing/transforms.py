import os

import cv2
import numpy as np
import spams

from pathml.preprocessing.utils import RGB_to_GREY, RGB_to_HSV, normalize_matrix_cols, RGB_to_OD

from pathml.core import Chunk


# Base class
# TODO move this to pathml.core
class Transform:
    """
    Base class for all Transforms.
    Each transform must operate on a chunk.
    """
    def __repr__(self):
        return "Base class for all transforms"

    def F(self, input):
        """functional implementation"""
        raise NotImplementedError

    def apply(self, chunk):
        """modify chunk"""
        raise NotImplementedError


# implement transforms here

class MedianBlur(Transform):
    """
    Median blur transform

    Args:
        kernel_size (int): Width of kernel. Must be an odd number. Defaults to 5.
    """
    def __init__(self, kernel_size=5):
        assert kernel_size % 2 == 1, "kernel_size must be an odd number"
        self.kernel_size = kernel_size

    def __repr__(self):
        return f"MedianBlur(kernel_size={self.kernel_size})"

    def F(self, image):
        assert image.dtype == np.uint8, f"image dtype {image.dtype} must be np.uint8"
        return cv2.medianBlur(image, ksize = self.kernel_size)

    def apply(self, chunk):
        assert isinstance(chunk, Chunk), f"argument of type {type(chunk)} must be a pathml.core.Chunk object."
        chunk.image = self.F(chunk.image)


class GaussianBlur(Transform):
    """
    Gaussian blur transform

    Args:
        kernel_size (int): Width of kernel. Must be an odd number. Defaults to 5.
        sigma (float): Variance of Gaussian kernel. Variance is assumed to be equal in X and Y axes. Defaults to 5.
    """
    def __init__(self, kernel_size=5, sigma=5):
        self.k_size = kernel_size
        self.sigma = sigma

    def __repr__(self):
        return f"GaussianBlur(kernel_size={self.k_size}, sigma={self.sigma})"

    def F(self, image):
        assert image.dtype == np.uint8, f"image dtype {image.dtype} must be np.uint8"
        out = cv2.GaussianBlur(image, ksize = (self.k_size, self.k_size), sigmaX = self.sigma, sigmaY = self.sigma)
        return out

    def apply(self, chunk):
        assert isinstance(chunk, Chunk), f"argument of type {type(chunk)} must be a pathml.core.Chunk object."
        chunk.image = self.F(chunk.image)


class BoxBlur(Transform):
    """
    Box blur transform. Averages each pixel with nearby pixels.

    Args:
        kernel_size (int): Width of kernel. Defaults to 5.
    """
    def __init__(self, kernel_size=5):
        self.kernel_size = kernel_size

    def __repr__(self):
        return f"BoxBlur(kernel_size={self.kernel_size})"

    def F(self, image):
        assert image.dtype == np.uint8, f"image dtype {image.dtype} must be np.uint8"
        return cv2.boxFilter(image, ksize = (self.kernel_size, self.kernel_size), ddepth = -1)

    def apply(self, chunk):
        assert isinstance(chunk, Chunk), f"argument of type {type(chunk)} must be a pathml.core.Chunk object."
        chunk.image = self.F(chunk.image)


class BinaryThreshold(Transform):
    """
    Binary thresholding transform.
    If input image is RGB it is first converted to greyscale, otherwise the input must have 1 channel.
    Creates a new mask.

    Args:
        use_otsu (bool): Whether to use Otsu's method to automatically determine optimal threshold. Defaults to True.
        threshold (int): Specified threshold. Ignored if use_otsu==True. Defaults to 0.
        mask_name (str): Name of mask that is created.

    References:
        Otsu, N., 1979. A threshold selection method from gray-level histograms. IEEE transactions on systems,
        man, and cybernetics, 9(1), pp.62-66.
    """
    def __init__(self, use_otsu=True, threshold=0, mask_name=None):
        self.threshold = threshold
        self.max_value = 255
        self.use_otsu = use_otsu
        if use_otsu:
            self.type = cv2.THRESH_BINARY + cv2.THRESH_OTSU
        else:
            self.type = cv2.THRESH_BINARY
        self.mask_name = mask_name

    def __repr__(self):
        return f"BinaryThreshold(use_otsu={self.use_otsu}, threshold={self.threshold}, mask_name={self.mask_name})"

    def F(self, image):
        assert image.dtype == np.uint8, f"image dtype {image.dtype} must be np.uint8"
        assert image.ndim == 2, f"input image has shape {image.shape}. Must convert to 1-channel image (H, W)."
        _, out = cv2.threshold(src = image, thresh = self.threshold, maxval = self.max_value, type = self.type)
        return out.astype(np.uint8)

    def apply(self, chunk):
        assert isinstance(chunk, Chunk), f"argument of type {type(chunk)} must be a pathml.core.Chunk object."
        assert self.mask_name is not None, f"Must enter a mask name"
        # TODO fix this type checking
        if chunk.slidetype == "RGB":
            im = RGB_to_GREY(chunk.image)
        else:
            im = np.squeeze(chunk.image)
            assert im.ndim == 2, "chunk.image is not RGB and has more than 1 channel"
        thresholded_mask = self.F(im)
        chunk.masks.add(key = self.mask_name, mask = thresholded_mask)


class MorphOpen(Transform):
    """
    Applies morphological opening to a mask.

    Args:
        kernel_size (int): Size of kernel for default square kernel. Ignored if a custom kernel is specified.
            Defaults to 5.
        n_iterations (int): Number of opening operations to perform. Defaults to 1.
        custom_kernel (np.ndarray): Optionally specify a custom kernel to use instead of default square kernel.
        mask_name (str): Name of mask on which to apply transform
    """
    def __init__(self, kernel_size=5, n_iterations=1, custom_kernel=None, mask_name=None):
        self.kernel_size = kernel_size
        self.n_iterations = n_iterations
        self.custom_kernel = custom_kernel
        self.mask_name = mask_name

    def __repr__(self):
        return f"MorphOpen(kernel_size={self.kernel_size}, n_iterations={self.n_iterations}, " \
               f"custom_kernel={self.custom_kernel}, mask_name={self.mask_name})"

    def F(self, mask):
        assert mask.dtype == np.uint8, f"mask type {mask.dtype} must be np.uint8"
        if self.custom_kernel is None:
            k = np.ones(self.kernel_size, dtype = np.uint8)
        else:
            k = self.custom_kernel
        out = cv2.morphologyEx(src = mask, kernel = k, op = cv2.MORPH_OPEN, iterations = self.n_iterations)
        return out

    def apply(self, chunk):
        assert self.mask_name is not None, f"Must enter a mask name"
        m = chunk.masks[self.mask_name]
        out = self.F(m)
        chunk.masks[self.mask_name] = out


class MorphClose(Transform):
    """
    Applies morphological closing to a mask.

    Args:
        kernel_size (int): Size of kernel for default square kernel. Ignored if a custom kernel is specified.
            Defaults to 5.
        n_iterations (int): Number of opening operations to perform. Defaults to 1.
        custom_kernel (np.ndarray): Optionally specify a custom kernel to use instead of default square kernel.
        mask_name (str): Name of mask on which to apply transform
    """

    def __init__(self, kernel_size=5, n_iterations=1, custom_kernel=None, mask_name=None):
        self.kernel_size = kernel_size
        self.n_iterations = n_iterations
        self.custom_kernel = custom_kernel
        self.mask_name = mask_name

    def __repr__(self):
        return f"MorphClose(kernel_size={self.kernel_size}, n_iterations={self.n_iterations}, " \
               f"custom_kernel={self.custom_kernel}, mask_name={self.mask_name})"

    def F(self, mask):
        assert mask.dtype == np.uint8, f"mask type {mask.dtype} must be np.uint8"
        if self.custom_kernel is None:
            k = np.ones(self.kernel_size, dtype = np.uint8)
        else:
            k = self.custom_kernel
        out = cv2.morphologyEx(src = mask, kernel = k, op = cv2.MORPH_CLOSE, iterations = self.n_iterations)
        return out

    def apply(self, chunk):
        assert self.mask_name is not None, f"Must enter a mask name"
        m = chunk.masks[self.mask_name]
        out = self.F(m)
        chunk.masks[self.mask_name] = out


class ForegroundDetection(Transform):
    """
    Foreground detection for binary masks. Identifies regions that have a total area greater than
    specified threshold. Supports including holes within foreground regions, or excluding holes
    above a specified area threshold.

    Args:
        min_region_size (int): Minimum area of detected foreground regions, in pixels. Defaults to 5000.
        max_hole_size (int): Maximum size of allowed holes in foreground regions, in pixels.
            Ignored if outer_contours_only=True. Defaults to 1500.
        outer_contours_only (bool): If true, ignore holes in detected foreground regions. Defaults to False.
        mask_name (str): Name of mask on which to apply transform

    References:
        Lu, M.Y., Williamson, D.F., Chen, T.Y., Chen, R.J., Barbieri, M. and Mahmood, F., 2020. Data Efficient and
        Weakly Supervised Computational Pathology on Whole Slide Images. arXiv preprint arXiv:2004.09666.
    """

    def __init__(self, min_region_size=5000, max_hole_size=1500, outer_contours_only=False, mask_name=None):
        self.min_region_size = min_region_size
        self.max_hole_size = max_hole_size
        self.outer_contours_only = outer_contours_only
        self.mask_name = mask_name

    def __repr__(self):
        return f"ForegroundDetection(min_region_size={self.min_region_size}, max_hole_size={self.max_hole_size}," \
               f"outer_contours_only={self.outer_contours_only}, mask_name={self.mask_name})"

    def F(self, mask):
        assert mask.dtype == np.uint8, f"mask type {mask.dtype} must be np.uint8"
        mode = cv2.RETR_EXTERNAL if self.outer_contours_only else cv2.RETR_CCOMP
        contours, hierarchy = cv2.findContours(mask.copy(), mode = mode, method = cv2.CHAIN_APPROX_NONE)

        if hierarchy is None:
            # no contours found --> return empty mask
            mask_out = np.zeros_like(mask)
        elif self.outer_contours_only:
            # remove regions below area threshold
            contour_thresh = np.array([cv2.contourArea(c) > self.min_region_size for c in contours])
            final_contours = np.array(contours)[contour_thresh]
            out = np.zeros_like(mask, dtype = np.int8)
            # fill contours
            cv2.fillPoly(out, final_contours, 255)
            mask_out = out
        else:
            # separate outside and inside contours (region boundaries vs. holes in regions)
            # find the outside contours by looking for those with no parents (4th column is -1 if no parent)
            hierarchy = np.squeeze(hierarchy, axis = 0)
            outside_contours = hierarchy[:, 3] == -1
            hole_contours = ~outside_contours

            # outside contours must be above min_tissue_region_size threshold
            contour_size_thresh = [cv2.contourArea(c) > self.min_region_size for c in contours]
            # hole contours must be above area threshold
            hole_size_thresh = [cv2.contourArea(c) > self.max_hole_size for c in contours]
            # holes must have parents above area threshold
            hole_parent_thresh = [p in np.argwhere(contour_size_thresh).flatten() for p in hierarchy[:, 3]]

            # convert to np arrays so that we can do vectorized '&'. see: https://stackoverflow.com/a/22647006
            contours = np.array(contours)
            outside_contours = np.array(outside_contours)
            hole_contours = np.array(hole_contours)
            contour_size_thresh = np.array(contour_size_thresh)
            hole_size_thresh = np.array(hole_size_thresh)
            hole_parent_thresh = np.array(hole_parent_thresh)

            final_outside_contours = contours[outside_contours & contour_size_thresh]
            final_hole_contours = contours[hole_contours & hole_size_thresh & hole_parent_thresh]

            # now combine outside and inside contours into final mask
            out1 = np.zeros_like(mask, dtype = np.int8)
            out2 = np.zeros_like(mask, dtype = np.int8)
            # fill outside contours, inside contours, then subtract
            cv2.fillPoly(out1, final_outside_contours, 255)
            cv2.fillPoly(out2, final_hole_contours, 255)
            mask_out = (out1 - out2)

        return mask_out.astype(np.uint8)

    def apply(self, chunk):
        assert self.mask_name is not None, f"Must enter a mask name"
        m = chunk.masks[self.mask_name]
        mask_out = self.F(m)
        chunk.masks[self.mask_name] = mask_out


class SuperpixelInterpolation(Transform):
    """
    Divide input image into superpixels using SLIC algorithm, then interpolate each superpixel with average color.
    SLIC superpixel algorithm described in Achanta et al. 2012.

    Args:
        region_size (int): region_size parameter used for superpixel creation. Defaults to 10.
        n_iter (int): Number of iterations to run SLIC algorithm. Defaults to 30.

    References:
        Achanta, R., Shaji, A., Smith, K., Lucchi, A., Fua, P. and Süsstrunk, S., 2012. SLIC superpixels compared to
        state-of-the-art superpixel methods. IEEE transactions on pattern analysis and machine intelligence, 34(11),
        pp.2274-2282.
    """
    def __init__(self, region_size=10, n_iter=30):
        self.region_size = region_size
        self.n_iter = n_iter

    def __repr__(self):
        return f"SuperpixelInterpolation(region_size={self.region_size}, n_iter={self.n_iter})"

    def F(self, image):
        assert image.dtype == np.uint8, f"Input image dtype {image.dtype} must be np.uint8"
        # initialize slic class and iterate
        slic = cv2.ximgproc.createSuperpixelSLIC(image = image, region_size = self.region_size)
        slic.iterate(num_iterations = self.n_iter)
        labels = slic.getLabels()
        n_labels = slic.getNumberOfSuperpixels()
        out = image.copy()
        # TODO apply over channels instead of looping
        for i in range(n_labels):
            mask = labels == i
            for c in range(3):
                av = np.mean(image[:, :, c][mask])
                out[:, :, c][mask] = av
        return out

    def apply(self, chunk):
        chunk.image = self.F(chunk.image)


class StainNormalizationHE(Transform):
    """
    Normalize H&E stained images to a reference slide.
    Also can be used to separate hematoxylin and eosin channels.

    H&E images are assumed to be composed of two stains, each one having a vector of its characteristic RGB values.
    The stain matrix is a 3x2 matrix where the first column corresponds to the hematoxylin stain vector and the second
    corresponds to eosin stain vector. The stain matrix can be estimated from a reference image in a number of ways;
    here we provide implementations of two such algorithms from Macenko et al. and Vahadane et al.

    After estimating the stain matrix for an image_ref, the next step is to assign stain concentrations to each pixel.
    Each pixel is assumed to be a linear combination of the two stain vectors, where the coefficients are the
    intensities of each stain vector at that pixel. TO solve for the intensities, we use least squares in Macenko
    method and lasso in vahadane method.

    The image_ref can then be reconstructed by applying those pixel intensities to a stain matrix. This allows you to
    standardize the appearance of an image_ref by reconstructing it using a reference stain matrix. Using this method of
    normalization may help account for differences in slide appearance arising from variations in staining procedure,
    differences between scanners, etc. Images can also be reconstructed using only a single stain vector, e.g. to
    separate the hematoxylin and eosin channels of an H&E image_ref.

    This code is based in part on StainTools: https://github.com/Peter554/StainTools

    Args:
        target (str): one of 'normalize', 'hematoxylin', or 'eosin'. Defaults to 'normalize'
        stain_estimation_method (str): method for estimating stain matrix. Must be one of 'macenko' or 'vahadane'.
            Defaults to 'macenko'.
        optical_density_threshold (float): Threshold for removing low-optical density pixels when estimating stain
            vectors. Defaults to 0.15
        sparsity_regularizer (float): Regularization parameter for dictionary learning when estimating stain vector
            using vahadane method. Ignored if ``concentration_estimation_method!="vahadane"``. Defaults to 1.0
        angular_percentile (float): Percentile for stain vector selection when estimating stain vector
            using Macenko method. Ignored if ``concentration_estimation_method!="macenko"``. Defaults to 0.01
        regularizer_lasso (float): regularization parameter for lasso solver. Defaults to 0.01.
            Ignored if ``method != 'lasso'``
        background_intensity (int): Intensity of background light. Must be an integer between 0 and 255.
            Defaults to 245.
        stain_matrix_target_od (np.ndarray): Stain matrix for reference slide.
            Matrix of H and E stain vectors in optical density (OD) space.
            Stain matrix is (3, 2) and first column corresponds to hematoxylin.
            Default stain matrix can be used, or you can also fit to a reference slide of your choosing by calling
            :meth:`~pathml.preprocessing.stains.StainNormalizationHE.fit_to_reference`.
        max_c_target (np.ndarray): Maximum concentrations of each stain in reference slide.
            Default can be used, or you can also fit to a reference slide of your choosing by calling
            :meth:`~pathml.preprocessing.stains.StainNormalizationHE.fit_to_reference`.

    References:
        Macenko, M., Niethammer, M., Marron, J.S., Borland, D., Woosley, J.T., Guan, X., Schmitt, C. and Thomas, N.E.,
        2009, June. A method for normalizing histology slides for quantitative analysis. In 2009 IEEE International
        Symposium on Biomedical Imaging: From Nano to Macro (pp. 1107-1110). IEEE.

        Vahadane, A., Peng, T., Sethi, A., Albarqouni, S., Wang, L., Baust, M., Steiger, K., Schlitter, A.M., Esposito,
        I. and Navab, N., 2016. Structure-preserving color normalization and sparse stain separation for histological
        images. IEEE transactions on medical imaging, 35(8), pp.1962-1971.
    """

    def __init__(
            self,
            target="normalize",
            stain_estimation_method="macenko",
            optical_density_threshold=0.15,
            sparsity_regularizer=1.0,
            angular_percentile=0.01,
            regularizer_lasso=0.01,
            background_intensity=245,
            stain_matrix_target_od=np.array([[0.5626, 0.2159], [0.7201, 0.8012], [0.4062, 0.5581]]),
            max_c_target=np.array([1.9705, 1.0308])
    ):
        # verify inputs
        assert target.lower() in ["normalize", "eosin", "hematoxylin"], \
            f"Error input target {target} must be one of 'normalize', 'eosin', 'hematoxylin'"
        assert stain_estimation_method.lower() in ['macenko', 'vahadane'],\
            f"Error: input stain estimation method {stain_estimation_method} must be one of 'macenko' or 'vahadane'"
        assert 0 <= background_intensity <= 255, \
            f"Error: input background intensity {background_intensity} must be an integer between 0 and 255"

        self.target = target.lower()
        self.stain_estimation_method = stain_estimation_method.lower()
        self.optical_density_threshold = optical_density_threshold
        self.sparsity_regularizer = sparsity_regularizer
        self.angular_percentile = angular_percentile
        self.regularizer_lasso = regularizer_lasso
        self.background_intensity = background_intensity
        self.stain_matrix_target_od = stain_matrix_target_od
        self.max_c_target = max_c_target

    def __repr__(self):
        return f"StainNormalizationHE(target={self.target}, stain_estimation_method={self.stain_estimation_method}, " \
               f"optical_density_threshold={self.optical_density_threshold}, " \
               f"sparsity_regularizer={self.sparsity_regularizer}, angular_percentile={self.angular_percentile}, " \
               f"regularizer_lasso={self.regularizer_lasso}, background_intensity={self.background_intensity}, " \
               f"stain_matrix_target_od={self.stain_matrix_target_od}, max_c_target={self.max_c_target})"

    def fit_to_reference(self, image_ref):
        """
        Fit ``stain_matrix`` and ``max_c`` to a reference slide. This allows you to use a specific slide as the
        reference for stain normalization. Works by first estimating stain matrix from input reference image,
        then estimating pixel concentrations. Newly computed stain matrix and maximum concentrations are then used
        for any future color normalization.

        Args:
            image_ref (np.ndarray): RGB reference image
        """
        # first estimate stain matrix for reference image_ref
        stain_matrix = self._estimate_stain_vectors(image = image_ref)

        # next get pixel concentrations for reference image_ref
        C = self._estimate_pixel_concentrations(image = image_ref, stain_matrix = stain_matrix)

        # get max concentrations
        # actually use 99th percentile so it's more robust
        max_C = np.percentile(C, 99, axis = 0).reshape((1, 2))

        # put the newly determined stain matrix and max C matrix for reference slide into class attrs
        self.stain_matrix_target_od = stain_matrix
        self.max_c_target = max_C

    def _estimate_stain_vectors(self, image):
        """
        Estimate stain vectors using appropriate method

        Args:
            image (np.ndarray): RGB image
        """
        # first estimate stain matrix for reference image_ref
        if self.stain_estimation_method == "macenko":
            stain_matrix = self._estimate_stain_vectors_macenko(image)
        elif self.stain_estimation_method == "vahadane":
            stain_matrix = self._estimate_stain_vectors_vahadane(image)
        else:
            raise Exception(f"Error: input stain estimation method {self.stain_estimation_method} must be one of "
                            f"'macenko' or 'vahadane'")
        return stain_matrix

    def _estimate_pixel_concentrations(self, image, stain_matrix):
        """
        Estimate pixel concentrations from a given stain matrix using appropriate method

        Args:
            image (np.ndarray): RGB image
            stain_matrix (np.ndarray): matrix of H and E stain vectors in optical density (OD) space.
                Stain_matrix is (3, 2) and first column corresponds to hematoxylin by convention.
        """
        if self.stain_estimation_method == "macenko":
            C = self._estimate_pixel_concentrations_lstsq(image, stain_matrix)
        elif self.stain_estimation_method == "vahadane":
            C = self._estimate_pixel_concentrations_lasso(image, stain_matrix)
        else:
            raise Exception(f"Provided target {self.target} invalid")
        return C

    def _estimate_stain_vectors_vahadane(self, image):
        """
        Estimate stain vectors using dictionary learning method from Vahadane et al.

        Args:
            image (np.ndarray): RGB image
        """
        # convert to Optical Density (OD) space
        image_OD = RGB_to_OD(image)
        # reshape to (M*N)x3
        image_OD = image_OD.reshape(-1, 3)
        # drop pixels with low OD
        OD = image_OD[np.all(image_OD > self.optical_density_threshold, axis = 1)]

        # dictionary learning
        # need to first update
        # see https://github.com/dmlc/xgboost/issues/1715#issuecomment-420305786
        os.environ['KMP_DUPLICATE_LIB_OK'] = 'True'
        dictionary = spams.trainDL(X = OD.T, K = 2, lambda1 = self.sparsity_regularizer, mode = 2,
                                   modeD = 0, posAlpha = True, posD = True, verbose = False)
        dictionary = normalize_matrix_cols(dictionary)
        # order H and E.
        # H on first col.
        if dictionary[0, 0] > dictionary[1, 0]:
            dictionary = dictionary[:, [1, 0]]
        return dictionary

    def _estimate_stain_vectors_macenko(self, image):
        """
        Estimate stain vectors using Macenko method. Returns a (3, 2) matrix with first column corresponding to
        hematoxylin and second column corresponding to eosin in OD space.

        Args:
            image (np.ndarray): RGB image
        """
        # convert to Optical Density (OD) space
        image_OD = RGB_to_OD(image)
        # reshape to (M*N)x3
        image_OD = image_OD.reshape(-1, 3)
        # drop pixels with low OD
        OD = image_OD[np.all(image_OD > self.optical_density_threshold, axis = 1)]
        # get top 2 PCs. PCs are eigenvectors of covariance matrix
        try:
            _, v = np.linalg.eigh(np.cov(OD.T))
        except np.linalg.LinAlgError as err:
            print(f"Error in computing eigenvectors: {err}")
            raise
        pcs = v[:, 1:3]
        # project OD pixels onto plane of first 2 PCs
        projected = OD @ pcs
        # Calculate angle of each point on projection plane
        angles = np.arctan2(projected[:, 1], projected[:, 0])
        # get robust min and max angles
        max_angle = np.percentile(angles, 100 * (1 - self.angular_percentile))
        min_angle = np.percentile(angles, 100 * self.angular_percentile)
        # get vector of unit length pointing in that angle, in projection plane
        # unit length vector of angle theta is <cos(theta), sin(theta)>
        v_max = np.array([np.cos(max_angle), np.sin(max_angle)])
        v_min = np.array([np.cos(min_angle), np.sin(min_angle)])
        # project back to OD space
        stain1 = pcs @ v_max
        stain2 = pcs @ v_min
        # a heuristic to make the vector corresponding to hematoxylin first and the
        # one corresponding to eosin second
        if stain2[0] > stain1[0]:
            HE = np.array((stain2, stain1)).T
        else:
            HE = np.array((stain1, stain2)).T
        return HE

    def _estimate_pixel_concentrations_lstsq(self, image, stain_matrix):
        """
        estimate concentrations of each stain at each pixel using least squares

        Args:
            image (np.ndarray): RGB image
            stain_matrix (np.ndarray): matrix of H and E stain vectors in optical density (OD) space.
                Stain_matrix is (3, 2) and first column corresponds to hematoxylin by convention.
        """
        image_OD = RGB_to_OD(image).reshape(-1, 3)

        # Get concentrations of each stain at each pixel
        # image_ref.T = S @ C.T
        #   image_ref.T is 3x(M*N)
        #   stain matrix S is 3x2
        #   concentration matrix C.T is 2x(M*N)
        # solve for C using least squares
        C = np.linalg.lstsq(stain_matrix, image_OD.T, rcond = None)[0].T
        return C

    def _estimate_pixel_concentrations_lasso(self, image, stain_matrix):
        """
        estimate concentrations of each stain at each pixel using lasso

        Args:
            image (np.ndarray): RGB image
            stain_matrix (np.ndarray): matrix of H and E stain vectors in optical density (OD) space.
                Stain_matrix is (3, 2) and first column corresponds to hematoxylin by convention.
        """
        image_OD = RGB_to_OD(image).reshape(-1, 3)

        # Get concentrations of each stain at each pixel
        # image_ref.T = S @ C.T
        #   image_ref.T is 3x(M*N)
        #   stain matrix S is 3x2
        #   concentration matrix C.T is 2x(M*N)
        # solve for C using lasso
        lamb = self.regularizer_lasso
        C = spams.lasso(X = image_OD.T, D = stain_matrix, mode = 2, lambda1 = lamb, pos = True).toarray().T
        return C

    def _reconstruct_image(self, pixel_intensities):
        """
        Reconstruct an image from pixel intensities. Uses reference stain matrix and max_c
        from `fit_to_reference`, if that method has been called, otherwise uses defaults.

        Args:
            pixel_intensities (np.ndarray): matrix of stain intensities for each pixel.
            If image_ref is MxN, stain matrix is 2x(M*M)
        """
        # scale to max intensities
        # actually use 99th percentile so it's more robust
        max_c = np.percentile(pixel_intensities, 99, axis = 0).reshape((1, 2))
        pixel_intensities *= (self.max_c_target / max_c)

        if self.target == "normalize":
            im = np.exp(-self.stain_matrix_target_od @ pixel_intensities.T)
        elif self.target == "hematoxylin":
            im = np.exp(- self.stain_matrix_target_od[:, 0].reshape(-1, 1) @ pixel_intensities[:, 0].reshape(-1, 1).T)
        elif self.target == "eosin":
            im = np.exp(- self.stain_matrix_target_od[:, 1].reshape(-1, 1) @ pixel_intensities[:, 1].reshape(-1, 1).T)
        else:
            raise Exception(
                f"Error: input target {self.target} is invalid. Must be one of 'normalize', 'eosin', 'hematoxylin'"
            )

        im = im * self.background_intensity
        im = np.clip(im, a_min = 0, a_max = 255)
        im = im.T.astype(np.uint8)
        return im

    def F(self, image):
        # first estimate stain matrix for reference image_ref
        stain_matrix = self._estimate_stain_vectors(image = image)

        # next get pixel concentrations for reference image_ref
        C = self._estimate_pixel_concentrations(image = image, stain_matrix = stain_matrix)

        # next reconstruct the image_ref
        im_reconstructed = self._reconstruct_image(pixel_intensities = C)

        im_reconstructed = im_reconstructed.reshape(image.shape)
        return im_reconstructed

    def apply(self, chunk):
        assert chunk.slidetype == "HE", f"Input chunk has slidetype {chunk.slidetype}. Must be HE"
        chunk.image = self.F(chunk.image)




class NucleusDetectionHE(Transform):
    """
    Simple nucleus detection algorithm for H&E stained images.
    Works by first separating hematoxylin channel, then doing interpolation using superpixels,
    and finally using Otsu's method for binary thresholding.

    Args:
        stain_estimation_method (str): Method for estimating stain matrix. Defaults to "vahadane"
        superpixel_region_size (int): region_size parameter used for superpixel creation. Defaults to 10.
        n_iter (int): Number of iterations to run SLIC superpixel algorithm. Defaults to 30.
        mask_name (str): Name of mask that is created.
        stain_kwargs (dict): other arguments passed to ``StainNormalizationHE()``

    References:
        Hu, B., Tang, Y., Eric, I., Chang, C., Fan, Y., Lai, M. and Xu, Y., 2018. Unsupervised learning for cell-level
        visual representation in histopathology images with generative adversarial networks. IEEE journal of
        biomedical and health informatics, 23(3), pp.1316-1328.
    """

    def __init__(self, stain_estimation_method="vahadane", superpixel_region_size=10,
                 n_iter=30, mask_name=None, **stain_kwargs):
        self.stain_estimation_method = stain_estimation_method
        self.superpixel_region_size = superpixel_region_size
        self.n_iter = n_iter
        self.stain_kwargs = stain_kwargs
        self.mask_name = mask_name

    def __repr__(self):
        return f"NucleusDetectionHE(stain_estimation_method={self.stain_estimation_method}, " \
               f"superpixel_region_size={self.superpixel_region_size}, n_iter={self.n_iter}, " \
               f"stain_kwargs={self.stain_kwargs})"

    def F(self, image):
        assert image.dtype == np.uint8, f"Input image dtype {image.dtype} must be np.uint8"
        im_hematoxylin = StainNormalizationHE(
            target = "hematoxylin", stain_estimation_method = self.stain_estimation_method, **self.stain_kwargs
        ).F(image)
        im_interpolated = SuperpixelInterpolation(
            region_size = self.superpixel_region_size, n_iter = self.n_iter
        ).F(im_hematoxylin)
        thresholded = BinaryThreshold(use_otsu = True).F(im_interpolated)
        # flip sign so that nuclei regions are TRUE (255)
        thresholded = ~thresholded
        return thresholded

    def apply(self, chunk):
        assert isinstance(chunk, Chunk), f"argument of type {type(chunk)} must be a pathml.core.Chunk object."
        assert chunk.slidetype == "HE", f"Input chunk has slidetype {chunk.slidetype}. Must be HE"
        assert self.mask_name is not None, f"Must enter a mask name"
        nucleus_mask = self.F(chunk.image)
        chunk.masks.add(key = self.mask_name, mask = nucleus_mask)


class TissueDetectionHE(Transform):
    """
    Detect tissue regions from H&E stained slide.
    First applies a median blur, then binary thresholding, then morphological opening and closing, and finally
    foreground detection.

    Args:
        :param use_saturation (bool): Whether to convert to HSV and use saturation channel for tissue detection.
            If False, convert from RGB to greyscale and use greyscale image_ref for tissue detection. Defaults to True.
        blur_ksize (int): kernel size used to apply median blurring. Defaults to 15.
        threshold (int): threshold for binary thresholding. If None, uses Otsu's method. Defaults to None.
        morph_n_iter (int): number of iterations of morphological opening and closing to apply. Defaults to 3.
        morph_k_size (int): kernel size for morphological opening and closing. Defaults to 7.
        min_region_size (int): Minimum area of detected foreground regions, in pixels. Defaults to 5000.
        max_hole_size (int): Maximum size of allowed holes in foreground regions, in pixels.
            Ignored if outer_contours_only=True. Defaults to 1500.
        outer_contours_only (bool): If true, ignore holes in detected foreground regions. Defaults to False.
        mask_name (str): name for new mask
    """

    def __init__(self, use_saturation=True, blur_ksize=17, threshold=None, morph_n_iter=3, morph_k_size=7,
                 min_region_size=5000, max_hole_size=1500, outer_contours_only=False, mask_name=None):
        self.use_sat = use_saturation
        self.blur_ksize = blur_ksize
        self.threshold = threshold
        self.morph_n_iter = morph_n_iter
        self.morph_k_size = morph_k_size
        self.min_region_size = min_region_size
        self.max_hole_size = max_hole_size
        self.outer_contours_only = outer_contours_only
        self.mask_name = mask_name

    def __repr__(self):
        return f"TissueDetectionHE(use_sat = {self.use_sat}, blur_ksize = {self.blur_ksize}, " \
               f"threshold = {self.threshold}, morph_n_iter = {self.morph_n_iter}, " \
               f"morph_k_size = {self.morph_k_size}, min_region_size = {self.min_region_size}, " \
               f"max_hole_size = {self.max_hole_size}, outer_contours_only = {self.outer_contours_only}, " \
               f"mask_name = {self.mask_name})"

    def F(self, image):
        assert image.dtype == np.uint8, f"Input image dtype {image.dtype} must be np.uint8"
        # first get single channel image_ref
        if self.use_sat:
            one_channel = RGB_to_HSV(image)
            one_channel = one_channel[:, :, 1]
        else:
            one_channel = RGB_to_GREY(image)

        blurred = MedianBlur(kernel_size = self.blur_ksize).F(one_channel)
        if self.threshold is None:
            thresholded = BinaryThreshold(use_otsu = True).F(blurred)
        else:
            thresholded = BinaryThreshold(use_otsu = False, threshold = self.threshold).F(blurred)
        opened = MorphOpen(kernel_size = self.morph_k_size, n_iterations = self.morph_n_iter).F(thresholded)
        closed = MorphClose(kernel_size = self.morph_k_size, n_iterations = self.morph_n_iter).F(opened)
        tissue = ForegroundDetection(min_region_size = self.min_region_size, max_hole_size = self.max_hole_size,
                                     outer_contours_only = self.outer_contours_only).F(closed)
        return tissue

    def apply(self, chunk):
        assert chunk.slidetype == "HE"
        mask = self.F(chunk.image)
        chunk.masks.add(key = self.mask_name, mask = mask)
