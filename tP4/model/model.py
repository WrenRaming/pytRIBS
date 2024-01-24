import tP4.model._infile as _infile
import tP4.model._aux as _aux
import tP4.model._diagnose as _diagnose
import tP4.model._post as _post
import tP4.model._inout as _inout
from tP4.results.results import Results


class Model(object):
    """
    A tRIBS Model class.

    This class provides access to the underlying framework of a tRIBS (TIN-based Real-time Integrated Basin
    Simulator) simulation. It includes one nested class: Results. The Model class is initialized at the top-level to
    facilitate model setup, simultation, post-processing and can be used for mainpulating and generating multiple
    simulations in an efficient manner.

    Attributes:
        input_options (dict): A dictionary of the necessary keywords for a tRIBS .in file.
        model_input_file (str): Path to a template .in file with the specified paths for model results, inputs, etc.

    Methods:
         __init__(self, model_input_file):  # Constructor method
            :param model_input_file: Path to a template .in file.
            :type param1: str

        create_input(self):
             Creates a dictionary with tRIBS input options assigne to attribute input_options.

        get_input_var(self, var):
            Read variable specified by var from .in file.
            :param var: A keyword from the .in file.
            :type var: str
            :return: the line following the keyword argument from the .in file.
            :rtype: str

        read_node_list(self,file_path):
            Returns node list provide by .dat file.
            :param file_path: Relative or absolute file path to .dat file.
            :type file_path: str
            :return: List of nodes specified by .dat file
            :rtype: list

        def convert_to_datetime(starting_date):
            Returns a pandas date-time object.
            :param starting_date: The start date of a given model simulation, note needs to be in tRIBS format.
            :type starting_date: str
            :return: A pandas Timestamp object.

    """

    def __init__(self):
        # attributes
        self.options = _infile.create_input_file()  # input options for tRIBS model run
        self.geo = {"UTM_Zone": None, "EPSG": None, "Projection": None}  # Geographic properties of tRIBS model domain.

        # nested classes
        self.Results = Results(self)

    # SIMULATION METHODS
    def __getattr__(self, name):
        if name in self.options:
            return self.options[name]
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

    def __dir__(self):
        # Include the keys from the options dictionary and the methods of the class
        return list(
            set(super().__dir__() + list(self.options.keys()))) if self.options is not None else super().__dir__()

    ########################################
    # PRE-RUN DIAGNOSTICS
    ########################################
    def check_paths(self):
        """
        Print input/output options where path does not exist and checks stations descriptor and grid data files.
        """
        _diagnose.check_paths(self)

    ########################################
    # INPUT/OUTPUT
    ########################################

    # Input File
    def read_input_file(self, file_path):
        """
        Reads .in file for tRIBS model simulation and assigns values to options attribute.
        :param file_path: Path to .in file.
        """
        _inout.read_input_file(self, file_path)

    def write_input_file(self, output_file_path):
        """
        Writes .in file for tRIBS model simulation.
        :param output_file_path: Location to write input file to.
        """
        _inout.write_input_file(self, output_file_path)

    # Mesh Related
    def read_point_files(self):
        """
        Returns geopandas dataframe of nodes or point used in tRIBS mesh.
        """
        gdf = _inout.read_point_files(self)
        return gdf

    @staticmethod
    def read_node_list(file_path):
        """
        Returns node list provide by .dat file.

        The node list can be further modified or used for reading in element/pixel files and subsequent processing.

        :param file_path: Relative or absolute file path to .dat file.
        :type file_path: str
        :return: List of nodes specified by .dat file
        :rtype: list
        """
        node_list = _inout.read_node_list(file_path)
        return node_list

    # Forcings
    def read_precip_sdf(self, file_path=None):
        """
        Returns list of precip stations, where information from each station is stored in a dictionary.
        :param file_path: Reads from options["hydrometstations"]["value"], but can be separately specified.
        :return: List of dictionaries.
        """
        list = _inout.read_precip_sdf(self, file_path)
        return list

    @staticmethod
    def read_precip_station(file_path):
        """
        Returns pandas dataframe of precipitation from a station specified by file_path.
        :param file_path: Flat file with columns Y M D H R
        :return: Pandas dataframe
        """
        df = _inout.read_precip_station(file_path)
        return df

    @staticmethod
    def write_precip_sdf(station_list, output_file_path):
        """
        Writes a list of precip stations to a flat file.
        :param station_list: List of dictionaries containing station information.
        :param output_file_path: Output flat file path.
        """
        _inout.write_precip_sdf(station_list, output_file_path)

    @staticmethod
    def write_precip_station(df, output_file_path):
        """
        Converts a DataFrame with 'date' and 'R' columns to flat file format with columns Y M D H R.
        :param df: Pandas DataFrame with 'date' and 'R' columns.
        :param output_file_path: Output flat file path.
        """
        _inout.write_precip_sdf(df, output_file_path)

    def read_met_sdf(self, file_path=None):
        """
        Returns list of met stations, where information from each station is stored in a dictionary.
        :param file_path: Reads from options["hydrometstations"]["value"], but can be separately specified.
        :return: List of dictionaries.
        """
        list_dict = _inout.read_met_sdf(self, file_path)
        return list_dict

    @staticmethod
    def read_met_file(file_path):
        """
        Returns pandas dataframe of meterological data file
        :param file_path: Path to meterological data file
        :return: dataframe
        """
        df = _inout.read_met_station(file_path)
        return df

    def read_grid_data_file(self, grid_type):
        """
        Returns dictionary with content of a specified Grid Data File (.gdf)
        :param grid_type: string set to "weather", "soil", of "land", with each corresponding to HYDROMETGRID, SCGRID, LUGRID
        :return: dictionary containg keys and content: "Number of Parameters","Latitude", "Longitude","GMT Time Zone", "Parameters" (a  list of dicts)
        """
        dictionary = _inout.read_grid_data_file(self, grid_type)
        return dictionary

    @staticmethod
    def read_ascii(file_path):
        """
        Returns dictionary containing 'data', 'profile', and additional metadata.
        :param file_path: Path to ASCII raster.
        :return: Dict
        """
        dictionary = _inout.read_ascii(file_path)
        return dictionary

    @staticmethod
    def write_ascii(raster_dict, output_file_path):
        """
        Writes raster data and metadata from a dictionary to an ASCII raster file.
        :param raster_dict: Dictionary containing 'data', 'profile', and additional metadata.
        :param output_file_path: Output ASCII raster file path.
        """
        _inout.write_ascii(raster_dict, output_file_path)

    ########################################
    # POST-RUN PROCESSING
    ########################################

    def read_voi_file(self, filename=None):
        """
        Returns GeoDataFrame containing voronoi polygons from tRIBS model domain.
        :param filename: Set to read _reach file specified from OUTFILENAME,but can be changed.
        :return: GeoDataFrame
        """
        gdf = _post.read_voi_file(self, filename)

        return gdf

    def read_reach_file(self, filename=None):
        """
        Returns GeoDataFrame containing reaches from tRIBS model domain.
        :param filename: Set to read _reach file specified from OUTFILENAME,but can be changed.
        :return: GeoDataFrame
        """
        gdf = _post.read_reach_file(self, filename)
        return gdf

    def merge_parallel_voi(self, join=None, result_path=None, format=None, save=False):
        """
        Returns geodataframe of merged vornoi polygons from parallel tRIBS model run.

        :param join: Data frame of dynamic or integrated tRIBS model output (optional).
        :param save: Set to True to save geodataframe (optional, default True).
        :param result_path: Path to save geodateframe (optional, default OUTFILENAME).
        :param format: Driver options for writing geodateframe (optional, default = ESRI Shapefile)

        :return: GeoDataFrame
        """

        gdf = _post.merge_parllel_voi(self, join, result_path, format, save)

        return gdf

    def merge_parallel_spatial_files(self, suffix="_00d", dtime=0, write=True, header=True, colnames=None,
                                     single=True):
        """
        Returns dictionary of combined spatial outputs for intervals specified by tRIBS option: "SPOPINTRVL".
        :param str suffix: Either _00d for dynamics outputs or _00i for time-integrated ouputs.
        :param int dtime : Option to specify time step at which to start merge of files.
        :param bool write: Option to write dataframes to file.
        :param bool header: Set to False if headers are not provided with spatial files.
        :param bool colnames: If header = False, column names can be provided for the dataframe--but it is expected the first column is ID.
        :param bool single: If single = True then only spatial files specified at dtime are merged.
        :return: Dictionary of pandas dataframes.
        """
        _dict = _post.merge_parllel_spatial_files(self, suffix, dtime, write, header, colnames,
                                                  single)
        return _dict

    ########################################
    # AUXILIARY METHODS
    ########################################
    @staticmethod
    def convert_to_datetime(starting_date):
        """
        Returns a pandas date-time object.

        :param starting_date: The start date of a given model simulation, note needs to be in tRIBS format.
        :type starting_date: str
        :rtupe: A pandas Timestamp object
        """
        date = _aux.convert_to_datetime(starting_date)
        return date

    def print_tags(self, tag_name):
        """
        Prints .in options for a specified tag.
        :param tag_name: Currently: "io", input/output, "physical", physical model params, "time", time parameters,
        "opts", parameters for model options, "restart", restart capabilities, "parallel", parallel options.

        Example:
            >>> m.print_tags("io")
        """
        _aux.print_tags(self, tag_name)

    @staticmethod
    def run(executable, input_file, mpi_command=None, tribs_flags=None, log_path=None,
            store_input=None, timeit=True, verbose=True):
        """
        {_aux.run.__doc__}

        Parameters:
        - executable: The executable to run.
        - input_file: The input file.
        - mpi_command: MPI command (optional).
        - tribs_flags: TRIBS flags (optional).
        - log_path: Path to the log file (optional).
        - store_input: Store input (optional).
        - timeit: Enable timing (optional).
        - verbose: Enable verbose mode (optional).
        """
        _aux.run(executable, input_file, mpi_command, tribs_flags, log_path,
                 store_input, timeit, verbose)

    @staticmethod
    def build(source_file, build_directory, verbose=True, exe="tRIBS", parallel="ON", cxx_flags="-O2"):
        """
        {_aux.build.__doc__}

        Parameters:
        - source_file: The source file to build.
        - build_directory: The build directory.
        - verbose: Enable verbose mode (optional, default is True).
        - exe: Executable name (optional, default is "tRIBS").
        - parallel: Parallel build option (optional, default is "ON").
        - cxx_flags: C++ compilation flags (optional, default is "-O2").
        """
        _aux.build(source_file, build_directory, verbose, exe, parallel, cxx_flags)