import os
import shutil

import pandas as pd
from rasterio.windows import from_bounds
from scipy.interpolate import RegularGridInterpolator
from scipy.spatial import cKDTree

from shapely.vectorized import contains
from math import ceil
from rasterio.mask import mask
import numpy as np
import geopandas as gpd
from rasterio.features import shapes
from whitebox import WhiteboxTools
from shapely.geometry import Point
import rasterio
import pywt
import pyvista as pv
from shapely.ops import unary_union

from pytRIBS.shared.inout import InOut

from pytRIBS.shared.shared_mixin import Meta, SharedMixin
from pytRIBS.mesh.run_docker import MeshBuilderDocker


class Preprocess:
    def __init__(self, outlet, snap_distance, threshold_area, name, dem_path, verbose_mode, meta=None,
                 dir_proccesed=None):

        self.outlet = outlet
        self.snap_distance = snap_distance
        self.threshold_area = threshold_area

        if meta is None:
            Meta.__init__(self)

        self.wbt = WhiteboxTools()
        self.wbt.set_verbose_mode(verbose_mode)

        if name is None:
            name = 'Basin'

        self.meta['Name'] = name

        if dir_proccesed is None:
            dir_proccesed = 'preprocessing'
            os.makedirs(dir_proccesed, exist_ok=True)

        if dem_path is not None:
            with rasterio.open(dem_path) as src:
                crs = src.crs
                self.meta['EPSG'] = crs.to_epsg()

        self.dem_preprocessing = dem_path
        self.output_dir = dir_proccesed

    def fill_depressions(self, output_path=None):
        """
        Fill Sinks within the watershed and plot the DEM afterwards
        """
        wbt = self.wbt
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_filled.tif'

        wbt.fill_depressions(self.dem_preprocessing, os.path.abspath(output_path), fix_flats=True)

        return output_path

    def create_outlet(self, x, y, flow_accumulation_raster, snap_distance, output_path=None):
        """
        Uses pour point coordinates to create shapefile of the pour point and plot it accordingly
        """
        pour_point_geometry = Point(x, y)
        pour_point_gdf = gpd.GeoDataFrame(geometry=[pour_point_geometry])
        pour_point_gdf.set_crs(epsg=self.meta['EPSG'], inplace=True)
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_outlet.shp'

        pour_point_gdf.to_file(output_path)

        wbt = self.wbt
        wbt.snap_pour_points(os.path.abspath(output_path), os.path.abspath(flow_accumulation_raster),
                             os.path.abspath(output_path), snap_distance)

        return output_path

    def generate_flow_direction_raster(self, filled_dem, output_path=None):
        """"
        Creates the flow direction raster based on the D8 method and plot it
        """
        wbt = self.wbt
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_d8.tif'

        wbt.d8_pointer(os.path.abspath(filled_dem), os.path.abspath(output_path), esri_pntr=True)

        return output_path

    def generate_flow_accumulation_raster(self, flow_direction_raster, output_path=None):
        """
        Create the flow accumulation raster using the flow direction raster obtained from D8 method
        """
        wbt = self.wbt
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_flow_acc.tif'

        wbt.d8_flow_accumulation(os.path.abspath(flow_direction_raster), os.path.abspath(output_path),
                                 pntr=True, esri_pntr=True)

        return output_path

    def generate_streams_raster(self, flow_accumulation_raster, threshold_area, output_path=None):
        """
        Obtain the stream raster from the flow accumulation raster based on the stream threshold provided before
        """
        wbt = self.wbt
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_stream.tif'

        wbt.extract_streams(
            os.path.abspath(flow_accumulation_raster),
            os.path.abspath(output_path),
            threshold_area
        )

        return output_path

    def generate_watershed_mask(self, flow_direction_raster, pour_point_shp, output_path=None):
        """
        Use the pour point shapefile and the flow direction raster to delineate the watershed in the form of a raster
        """
        wbt = self.wbt
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_watershed_msk.tif'

        wbt.watershed(os.path.abspath(flow_direction_raster), os.path.abspath(pour_point_shp),
                      os.path.abspath(output_path), esri_pntr=True)

        return output_path

    def generate_watershed_boundary(self, watershed_mask, output_path=None):
        """
        Develop the watershed boundary shapefile from the watershed raster
        """
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_watershed_bound.tif'

        with rasterio.open(watershed_mask) as src:
            image = src.read(1)  # Read the first band
            mask = image != src.nodata  # Create a mask for valid data values

            results = (
                {'properties': {'raster_val': v}, 'geometry': s}
                for i, (s, v) in enumerate(
                shapes(image, mask=mask, transform=src.transform))
            )

            # Convert the results to a GeoDataFrame
            geoms = list(results)
            gdf = gpd.GeoDataFrame.from_features(geoms)
            gdf = gdf.dissolve()

        gdf.to_file(output_path)

        return gdf, output_path

    def convert_stream_raster_to_vector(self, stream_raster, flow_direction_raster, output_path=None):
        """
        Create a shapefile of the stream network from the stream raster
        """
        wbt = self.wbt
        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_streams.shp'

        # Convert Stream Raster to Vector
        wbt.raster_streams_to_vector(
            os.path.abspath(stream_raster),
            os.path.abspath(flow_direction_raster),
            os.path.abspath(output_path),
            esri_pntr=True
        )

        return output_path

    def clip_rasters(self, raster_list, watershed_boundary, method='boundary', output_dir=None):
        """
        Using the watershed boundary polygon to clip the filled dem, flow direction raster, stream raster and stream order raster
        """

        if output_dir is None:
            output_dir = f'{self.output_dir}/'

        name = self.meta['Name']
        ws_bound = gpd.read_file(watershed_boundary)
        geometry = [unary_union(ws_bound.geometry)]
        bounds = ws_bound.total_bounds  # [minx, miny, maxx, maxy]

        for raster_file in raster_list:

            with rasterio.open(raster_file) as src:
                if method == 'boundary' or method == 'both':
                    output_raster = f'{output_dir}/{name}_clipped.tif'

                    clipped_data, clipped_transform = mask(src, geometry, crop=True)

                    clipped_profile = src.profile
                    clipped_profile.update({
                        'height': clipped_data.shape[1],
                        'width': clipped_data.shape[2],
                        'transform': clipped_transform
                    })

                    with rasterio.open(output_raster, 'w', **clipped_profile) as dst:
                        dst.write(clipped_data)

                if method == 'extent' or method == 'both':
                    output_raster = f'{output_dir}/{name}_clipped_ext.tif'

                    window = from_bounds(*bounds, transform=src.transform)

                    clipped_data = src.read(window=window)
                    clipped_transform = src.window_transform(window)
                    clipped_meta = src.meta.copy()

                    # Update the metadata with the new dimensions and transform
                    clipped_meta.update({
                        "driver": "GTiff",
                        "height": clipped_data.shape[1],
                        "width": clipped_data.shape[2],
                        "transform": clipped_transform
                    })

                    # Save the clipped raster to the output path
                    with rasterio.open(output_raster, "w", **clipped_meta) as dst:
                        dst.write(clipped_data)

    def clip_streamline(self, stream_shapefile, watershed_boundary, output_path=None):
        """
        Streamlines shapefile to be clipped by watershed boundary polygon
        """

        name = self.meta['Name']

        if output_path is None:
            output_path = f'{self.output_dir}/{name}_streams.shp'

        lines = gpd.read_file(stream_shapefile)
        watershed_boundary_t = gpd.read_file(watershed_boundary)
        clipped_lines = gpd.clip(lines, watershed_boundary_t)
        clipped_lines.to_file(output_path)

        return output_path

    def extract_watershed_and_stream_network(self, outlet_path, boundary_path, output_streams_path, clean=True):

        output_dir = self.output_dir

        if clean is True:
            temp = self.output_dir + '/temp'
            os.makedirs(temp, exist_ok=False)
            self.output_dir = temp

        filled = self.fill_depressions()
        d8_raster = self.generate_flow_direction_raster(filled)
        flow_acc = self.generate_flow_accumulation_raster(d8_raster)
        streams = self.generate_streams_raster(flow_acc, self.threshold_area)
        outlet = self.create_outlet(self.outlet[0], self.outlet[1], flow_acc, self.snap_distance,
                                    output_path=f'{outlet_path}')
        ws_mask = self.generate_watershed_mask(d8_raster, outlet)
        _, ws_bound = self.generate_watershed_boundary(ws_mask, output_path=f'{boundary_path}')
        stream_shp = self.convert_stream_raster_to_vector(streams, d8_raster)
        self.clip_rasters([filled], ws_bound, output_dir=output_dir, method='both')
        self.clip_streamline(os.path.abspath(stream_shp), ws_bound, output_path=f'{output_streams_path}')

        if clean is True:
            shutil.rmtree(temp)


class GenerateMesh:
    def __init__(self, path_to_raster, path_to_watershed, path_to_stream_network, path_to_outlet, maxlevel=None):
        self.normalizing_coeff = None
        self.raster = path_to_raster
        self.maxlevel = maxlevel
        self.extract_raster_and_wavelet_info()
        self.watershed = gpd.read_file(path_to_watershed)
        self.stream_network = gpd.read_file(path_to_stream_network)
        self.outlet = gpd.read_file(path_to_outlet)

    def extract_raster_and_wavelet_info(self):
        with rasterio.open(self.raster) as src:
            self.data = src.read(1)  # Read the first band
            self.transform = src.transform
            self.bounds = src.bounds
            self.width = src.width
            self.height = src.height

        self.wavelet_packet = pywt.WaveletPacket2D(data=self.data, wavelet='db1',
                                                   maxlevel=self.maxlevel)
        # update maxlevel incase it's none
        self.maxlevel = self.wavelet_packet.maxlevel
        self.normalizing_coeff = self.find_max_maximum_coeffs()

    def get_extent(self):

        x_min = self.bounds.left
        x_max = self.bounds.right
        y_min = self.bounds.bottom
        y_max = self.bounds.top

        return x_min, x_max, y_min, y_max

    def find_max_average_coeffs(self):
        max_avg_coeffs = []
        for level in range(1, self.maxlevel + 1):
            v = self.wavelet_packet['v' * level].data
            h = self.wavelet_packet['h' * level].data
            d = self.wavelet_packet['d' * level].data
            avg_coeffs = np.mean(np.abs([v, h, d]), axis=0)
            max_avg_coeffs.append(np.max(avg_coeffs))
        return max(max_avg_coeffs)

    def find_max_maximum_coeffs(self):
        max_coeffs = []
        for level in range(1, self.maxlevel + 1):
            v = self.wavelet_packet['v' * level].data
            h = self.wavelet_packet['h' * level].data
            d = self.wavelet_packet['d' * level].data
            avg_coeffs = np.max(np.abs([v, h, d]), axis=0)
            max_coeffs.append(np.max(avg_coeffs))
        return max(max_coeffs)

    def extract_points_from_significant_details(self, threshold):

        centers = set()
        for level in range(1, self.maxlevel + 1):
            centers.update(self._process_level(level, threshold))

        centers = np.array(list(centers))

        stream_points = self._generate_points_along_stream(centers)
        stream_code = np.ones(len(stream_points))*3


        med_distance, max_distance = self._distance_to_nearest_n(centers, n=6)

        centers, boundary_codes = self._filter_coords_within_geometry(centers, med_distance)

        x, y = self.outlet.geometry[0].xy
        out_points = [[x[0], y[0]]]
        out_code = 2

        centers = np.vstack((centers,stream_points, out_points))  # stream_points
        boundary_codes = np.hstack((boundary_codes,stream_code,out_code))  # stream_code

        unique_centers, unique_indices = np.unique(centers, axis=0, return_index=True)
        centers = unique_centers
        boundary_codes = boundary_codes[unique_indices]

        elevations = self.interpolate_elevations(centers)

        return np.column_stack((centers, elevations, boundary_codes))

    def _filter_coords_within_geometry(self, coords, buffer_distance):

        scale = 0.75
        original_watershed = self.watershed.geometry.iloc[0]
        buffered_watershed = original_watershed.buffer(buffer_distance * scale)

        num_boundary_points = int(ceil(buffered_watershed.length/(buffer_distance*scale)))

        # # this is needed to keep outlet exposed
        # x, y = self.outlet.geometry[0].xy
        # outlet_point = Point(x[0], y[0])
        # outlet_buffer = outlet_point.buffer(buffer_distance*1.5)
        #
        # buffered_watershed = buffered_watershed.difference(outlet_buffer)

        # boundary coords
        boundary_coords = np.array(list(
            buffered_watershed.exterior.interpolate(i / num_boundary_points, normalized=True).coords[0] for i in
            range(num_boundary_points)))

        boundary_codes = np.ones(boundary_coords.shape[0], dtype=int)

        within_original = contains(original_watershed, coords[:, 0], coords[:, 1])

        # because the buffered watershed is altered you can have closed nodes within the watershed
        bcoords_within_orignal = contains(original_watershed, boundary_coords[:, 0], boundary_coords[:, 1])

        boundary_coords = boundary_coords[~bcoords_within_orignal, :]
        boundary_codes = boundary_codes[~bcoords_within_orignal]

        all_coords = np.vstack([coords[within_original, :], boundary_coords])
        all_boundary_codes = np.concatenate([np.zeros(np.sum(within_original), dtype=int), boundary_codes])

        return all_coords, all_boundary_codes

    def _process_level(self, level, threshold):
        v = self.wavelet_packet['v' * level].data
        h = self.wavelet_packet['h' * level].data
        d = self.wavelet_packet['d' * level].data

        r, c = v.shape
        dx = (self.bounds.right - self.bounds.left) / c
        dy = (self.bounds.top - self.bounds.bottom) / r

        norm_coeffs = np.maximum.reduce([np.abs(v), np.abs(h), np.abs(d)]) / self.normalizing_coeff
        sig_mask = norm_coeffs > (2 ** (-level + 1) * threshold)

        rows, cols = np.where(sig_mask)
        x_coords = self.bounds.left + cols * dx
        y_coords = self.bounds.top - rows * dy

        return zip(x_coords, y_coords)

    @staticmethod
    def _distance_to_nearest_n(points, n=6):
        """
        Calculate the average distance to the nearest n points for each point in a list.

        Parameters:
        points (list of tuples): A list of (x, y) coordinates.
        n (int): The number of nearest neighbors to consider.

        Returns:
        list: A list of average distances to the nearest n points for each point.
        """
        points_array = np.array(points)
        tree = cKDTree(points_array)
        distances, _ = tree.query(points_array, k=n + 1)

        median_distance = np.max(np.median(distances[:, :], axis=0))
        max_distance = np.max(np.max(distances[:, :], axis=0))

        return median_distance, max_distance

    def convert_coords_to_mesh(self, coords):

        points = coords[:, :3]  # First three columns are x, y, z
        boundary_codes = coords[:, 3]  # Fourth column is boundary code

        point_cloud = pv.PolyData(points)

        elevation = points[:, 2]
        # elevation[boundary_codes == 1] = np.nan  # Set elevation to NaN where boundary code is 1
        point_cloud['Elevation'] = elevation
        point_cloud['BoundaryCode'] = boundary_codes

        mesh = point_cloud.delaunay_2d()

        return mesh

    def interpolate_elevations(self, points):

        height, width = self.data.shape

        x = np.arange(width) * self.transform[0] + self.transform[2]
        y = np.arange(height) * self.transform[4] + self.transform[5]

        interpolator = RegularGridInterpolator((y, x), self.data, method='linear', bounds_error=False,
                                               fill_value=None)

        elevations = interpolator((points[:, 1], points[:, 0]))

        return elevations

    def _generate_points_along_stream(self, coords):
        """
        Generate points along the stream network ensuring they are sufficiently spaced.
        """

        stream = self.stream_network
        dem_res = self.transform[0]

        # Initialize the interior KDTree
        interior_tree = cKDTree(coords)  # Assumes coords is a NumPy array

        final_stream_pts = []

        for idx, row in stream.iterrows():
            # Extract line and compute points
            line = row['geometry']
            length = line.length
            num_points = int(ceil(length / dem_res))
            xy = [line.interpolate(i * dem_res) for i in range(num_points + 1)]
            stream_xy = np.array([[p.x, p.y] for p in xy])

            # Setup KDTree for stream points
            stream_tree = cKDTree(stream_xy)

            # Initialize stream points
            begin, end = stream_xy[0, :], stream_xy[-1, :]
            working_stream_pts = [begin, end]
            temp_stream_pts = [begin]

            # Check and remove close interior points
            dis_check, idx = stream_tree.query(coords, k=1)
            close_interior_pts = np.where(dis_check <= dem_res)[0]

            if len(close_interior_pts) > 0:
                coords_list = coords.tolist()
                for i in sorted(close_interior_pts, reverse=True):
                    temp_stream_pts.append(coords_list.pop(i))
                coords = np.array(coords_list)
                interior_tree = cKDTree(coords)

            # Initial conditions for while loop
            distance = np.linalg.norm(working_stream_pts[0] - working_stream_pts[1])
            dis_interior, _ = interior_tree.query(working_stream_pts[0], k=1)
            dis_stream, idx = stream_tree.query(working_stream_pts[0], k=len(stream_xy))
            idx_last = 0

            # Iterate to find additional stream points
            while distance > dis_interior:
                ids = idx[dis_stream < dis_interior]
                if len(ids) == 0:
                    break
                id_next = ids[-1]

                if id_next < idx_last:
                    id_next = ids[ids > idx_last][-1]

                temp_stream_pts.append(stream_xy[id_next])
                working_stream_pts = [stream_xy[id_next], end]
                idx_last = id_next

                distance = np.linalg.norm(working_stream_pts[0] - working_stream_pts[1])
                dis_interior, _ = interior_tree.query(working_stream_pts[0], k=1)
                dis_stream, idx = stream_tree.query(working_stream_pts[0], k=len(stream_xy))

            temp_stream_pts.append(end)
            final_stream_pts.extend(temp_stream_pts)

        return final_stream_pts

    @staticmethod
    def convert_points_to_gdf(coords):
        df = pd.DataFrame(coords, columns=['x', 'y', 'elevation', 'bc'])
        df['geometry'] = df.apply(lambda row: Point(row['x'], row['y']), axis=1)
        gdf = gpd.GeoDataFrame(df, geometry='geometry')
        gdf = gdf.drop(columns=['x', 'y'])
        return gdf

    @staticmethod
    def write_point_file(gdf, output):
        InOut.write_point_file(gdf, output)

    @staticmethod
    def plot_mesh(mesh, scalar=None, **kwargs):
        plotter = SharedMixin.plot_mesh(mesh, scalar, **kwargs)

        return plotter

    @staticmethod
    def generate_meshbuild_input_file(filename, base_name, point_filename):
        with open(filename, 'w') as file:
            file.write("VELOCITYRATIO:\n")
            file.write(f"{str(1.2)}\n")
            file.write("BASEFLOW:\n")
            file.write(f"{str(0.2)}\n")
            file.write("VELOCITYCOEF:\n")
            file.write(f"{str(60)}\n")
            file.write("FLOWEXP:\n")
            file.write(f"{str(0.3)}\n")
            file.write("OUTFILENAME:\n")
            file.write(f"{base_name}\n")
            file.write("POINTFILENAME:\n")
            file.write(f"{point_filename}\n")

    @staticmethod
    def partition_mesh(volume, partition_args):
        '''
        @param volume: Path to directory containing .in and .points files
        @param partition_args: [<name of inpufile (
        str)>,<number of nodes (int)>,<partition methods 1-3 (int)>,<basename (str)>]
        @return: Produces a .reach file needed for running tRIBS in parallel mode
        '''
        current = os.getcwd()
        os.chdir(volume)

        meshbuild = MeshBuilderDocker(os.getcwd())
        meshbuild.start_docker_desktop()
        meshbuild.pull_image()
        meshbuild.run_container()
        meshbuild.execute_meshbuild_workflow(*partition_args)
        meshbuild.cleanup_container()
        # meshbuild.clean_directory()

        os.chdir(current)
