import numpy as np
import rasterio
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt

from pytRIBS.shared.aux import Aux
from pytRIBS.shared.inout import InOut


class _Land(InOut):
    @staticmethod
    def discrete_colormap(N, base_cmap=None):
        cmap = Aux.discrete_cmap(N, base_cmap)
        return cmap
    @staticmethod
    def unsupervised_classification_naip(image_path, output_file_path, method='NDVI', n_clusters=4,
                                         plot_result=True):
        """
        Perform unsupervised classification on a NAIP image using K-means clustering.

        :param image_path: Path to the NAIP image file.
        :type image_path: str
        :param output_file_path: Path to save the classified image.
        :type output_file_path: str
        :param method: Method to use for classification, 'NDVI' or 'true_color'. Default is 'NDVI'.
        :type method: str
        :param n_clusters: Number of clusters for K-means. Default is 5.
        :type n_clusters: int
        :param plot_result: Whether to plot the classified image. Default is True.
        :type plot_result: bool
        :return: Classified image with the same dimensions as input image.
        :rtype: np.ndarray
        """

        def classify_ndvi(image):
            """
            Calculate NDVI from NAIP image.
            """
            # Calculate NDVI
            red = image[0].astype(float)
            nir = image[1].astype(float)

            mask = (red == 0) & (nir == 0)

            red[mask] = np.nan
            nir[mask] = np.nan

            ndvi = (nir - red) / (nir + red)
            ndvi[np.isnan(ndvi)] = -9999  # Use a nodata value that can be handled

            return ndvi, mask

        with rasterio.open(image_path) as src:
            image = src.read()
            profile = src.profile

        if method == 'NDVI':
            data, mask = classify_ndvi(image)
            profile.update(count=1)
        elif method == 'true_color':
            n_bands, n_rows, n_cols = image.shape
            data = image.reshape(n_bands, -1).T
            mask = image[0] == 0
        else:
            raise ValueError("Method must be 'NDVI' or 'true_color'")

        if method == 'NDVI':
            reshaped_data = data.reshape(-1, 1)
        else:
            reshaped_data = data.reshape(n_bands, -1).T

        kmeans = KMeans(n_clusters=n_clusters, random_state=0)
        kmeans.fit(reshaped_data)
        labels = kmeans.labels_

        if method == 'NDVI':
            classified_image = labels.reshape(data.shape)
        else:
            classified_image = labels.reshape(n_rows, n_cols)

        profile.update(
            dtype=rasterio.uint8,
            count=1,
            compress='lzw'
        )

        InOut.write_ascii({'data': classified_image, 'profile': profile}, output_file_path)

        if plot_result:
            plt.figure(figsize=(10, 10))
            classified_image_masked = np.ma.masked_where(mask, classified_image)
            plt.imshow(classified_image_masked, cmap='viridis')
            plt.title('Classified Image')
            plt.axis('off')
            plt.show()

        classes = np.unique(classified_image)
        class_list = []

        for cl in classes:
            class_list.append({
                'ID': cl,
                'a': None,
                'b1': None,
                'P': None,
                'S': None,
                'K': None,
                'b2': None,
                'Al': None,
                'h': None,
                'Kt': None,
                'Rs': None,
                'V': None,
                'LAI': None,
                'theta*_s': None,
                'theta*_t': None
            })

        return classified_image, class_list

    @staticmethod
    def classify_vegetation_height(raster_path, thresholds, output_path, plot_result=True):
        """
        Classifies vegetation height raster based on user-defined thresholds.

        :param raster_path: str
            Path to the input tree height raster.

        :param thresholds: list of tuples
            Each tuple defines a range (min, max, class) and its class value.
            Example: ``[(0, 5, 1), (5, 10, 2), (10, 15, 3)]`` would classify heights
            from 0-5 as class 1, 5-10 as class 2, etc.
            - The min and max values must be increasing.
            - On the first iteration, min is allowed to equal max; otherwise, min must be
              greater than the previous max.

        :param output_path: str
            Path to save the classified raster.

        :param plot_result: bool, optional
            Whether to plot the classified image. Default is ``True``.

        :returns:
            - **classified_image** (*np.ndarray*): The classified raster array.
            - **class_list** (*list of dicts*): List of class attributes.

        :raises ValueError:
            If the min value is not greater than the previous max value, or if min equals
            max on any iteration other than the first.

        Example usage::

            thresholds = [(0, 5, 1), (5, 10, 2), (10, 15, 3)]
            classified_data, class_list = classify_vegetation_height(
                raster_path="path/to/raster.tif",
                thresholds=thresholds,
                output_path="path/to/output.tif"
            )
        """

        with rasterio.open(raster_path) as src:
            height_data = src.read(1)
            profile = src.profile

            classified_data = np.zeros_like(height_data, dtype=np.uint8)

            prev_max_val = None

            for i, (min_val, max_val, class_val) in enumerate(thresholds):
                if prev_max_val is not None:
                    if not (min_val >= prev_max_val or (i == 0 and min_val == max_val)):
                        raise ValueError(
                            "Min value must be greater than previous max value, or equal only on the first iteration.")

                if min_val != max_val:
                    classified_data[(height_data > min_val) & (height_data <= max_val)] = class_val
                elif i == 0 and min_val == max_val:
                    classified_data[(height_data == max_val)] = class_val
                else:
                    raise ValueError("Min and max can only be equal on the first iteration.")

                prev_max_val = max_val

            profile.update(dtype=rasterio.uint8, count=1, compress='lzw')

            InOut.write_ascii({'data': classified_data, 'profile': profile}, output_path)

        if plot_result:
            plt.figure(figsize=(10, 10))
            plt.imshow(classified_data, cmap='viridis')
            plt.title('Classified Vegetation Height')
            plt.axis('off')
            plt.show()

        classes = np.unique(classified_data)
        class_list = []

        for cl in classes:
            class_list.append({
                'ID': cl,
                'a': None,
                'b1': None,
                'P': None,
                'S': None,
                'K': None,
                'b2': None,
                'Al': None,
                'h': None,
                'Kt': None,
                'Rs': None,
                'V': None,
                'LAI': None,
                'theta*_s': None,
                'theta*_t': None
            })

        return classified_data, class_list
