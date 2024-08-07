import numpy as np
import rasterio
from sklearn.cluster import KMeans
import matplotlib.pyplot as plt
from pytRIBS.shared.inout import InOut


def unsupervised_classification_naip(image_path, output_file_path, method='NDVI', n_clusters=5, plot_result=True):
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

    def calculate_ndvi(image):
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
        data, mask = calculate_ndvi(image)
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
