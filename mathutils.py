from numpy import *


def compute_distance(n1, n2):
    """Calculate distance in km between two nodes using haversine forumla"""
    lat1, lon1 = n1[0], n1[1]
    lat2, lon2 = n2[0], n2[1]
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    d = math.sin(math.radians(dlat) * 0.5) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(math.radians(dlon) * 0.5) ** 2
    return math.asin(math.sqrt(d)) * 12742
    
    
def perp( a ) :
    b = empty_like(a)
    b[0] = -a[1]
    b[1] = a[0]
    return b

# line segment a given by endpoints a1, a2
# line segment b given by endpoints b1, b2
# return 
def seg_intersect(a1,a2, b1,b2) :
    da = a2-a1
    db = b2-b1
    dp = a1-b1
    dap = perp(da)
    denom = dot( dap, db)
    num = dot( dap, dp )
    return (num / denom.astype(float))*db + b1
    
def intersect(vectorA, vectorB):
    X1, Y1 = vectorA[0]
    X2, Y2 = vectorA[1]
    X3, Y3 = vectorB[0]
    X4, Y4 = vectorB[1]
    
    inter = seg_intersect(array([X1, Y1]), array([X2, Y2]), array([X3, Y3]), array([X4, Y4]))
    
    return inter[0]>=min(X3, X4) and inter[0]<=max(X3,X4) and inter[1]>=min(Y3, Y4) and inter[1]<=max(Y4,Y3) and inter[0]>=min(X1, X2) and inter[0]<=max(X1,X2) and inter[1]>=min(Y1, Y2) and inter[1]<=max(Y1,Y2)

def isRight(vectorA, vectorB):
    X1, Y1 = vectorA[0]
    X2, Y2 = vectorA[1]
    X3, Y3 = vectorB[0]
    X4, Y4 = vectorB[1]
    Ax = X2-X1
    Ay = Y2-Y1
    Bx = X4-X3
    By = Y4-Y3
    return -Ax * By + Ay * Bx > 0    
    
def isLeft(vectorA, vectorB):
    X1, Y1 = vectorA[0]
    X2, Y2 = vectorA[1]
    X3, Y3 = vectorB[0]
    X4, Y4 = vectorB[1]
    Ax = X2-X1
    Ay = Y2-Y1
    Bx = X4-X3
    By = Y4-Y3
    return -Ax * By + Ay * Bx < 0    
    
    
# Print iterations progress
def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print('\r%s |%s| %s%% %s' % (prefix, bar, percent, suffix), end = printEnd)
    # Print New Line on Complete
    if iteration == total: 
        print()    