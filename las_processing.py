from laspy.file import File
from scipy.spatial.kdtree import KDTree
import numpy as np
import matplotlib.pyplot as plt


def scaled_x_dimension(las_file):
    """ Grab just the X dimension from the file, and scale it. """

    x_dimension = las_file.X
    scale = las_file.header.scale[0]
    offset = las_file.header.offset[0]
    return x_dimension * scale + offset


def get_point_format(lasfile):
    """ Find out what the point format looks like """

    point_format = lasfile.point_format
    for spec in point_format:
        print(spec.name)


def get_header(lasfile):
    """ get the header format """

    header_format = lasfile.header.header_format
    for spec in header_format:
        print(spec.name)


def get_nearest(lasfile):
    """ return a nearest neighbor kdtree query """

    dataset = np.vstack([lasfile.x, lasfile.y, lasfile.z]).transpose()
    tree = KDTree(dataset)
    query = tree.query(dataset[100,], k=5)
    return query


def get_ground_points(lasfile):
    """ return a numpy array of ground points """
    
    num_returns = lasfile.num_returns
    return_num = lasfile.return_num
    ground_points = lasfile.points[num_returns == return_num]
    return ground_points


def main():
    """ Playing around with laspy """

    # input las
    inFile = File("las/L437_300FT_ROW_TXSP_S_NAD83_2011_USFT.las")

    # Grab all of the points from the file.
    point_records = inFile.points

    # scale x dimension
    scaled_x = scaled_x_dimension(inFile)

    # print point format
    get_point_format(inFile)

    # Lets take a look at the header also.
    get_header(inFile)

    # do a nearest neighbor analysis
    query = get_nearest(inFile)
    
    # get ground points
    ground_points = get_ground_points(inFile)
    
    print("%i points out of %i were ground points." % (len(ground_points),
                                                       len(inFile)))

    # plot a map of intensities
    plt.hist(inFile.intensity)
    plt.title("Histogram of the Intensity Dimension")
    plt.show()

if __name__ == '__main__':
    main()
