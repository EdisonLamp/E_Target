
#test values

from math import sqrt


p1_p2 = 30
p1_p3 = 46
p1_p4 = 27

#base values
dimentions_edge = 72

def calculate_possition(p1_p2, p1_p3, p1_p4, dimentions_edge):
    # Calculate the position based on the given values
    main_circe_r = (p1_p4**2 - p1_p2**2 - p1_p3**2) / (2 * (p1_p4 - p1_p2 - p1_p3))

    Y1 = (((main_circe_r+p1_p2)**2) + (dimentions_edge**2) - ((main_circe_r+p1_p3)**2)) / (2 * dimentions_edge)

    X1 = sqrt((main_circe_r+p1_p2)**2 - Y1**2)

    return X1, Y1, main_circe_r




def calculate_possition_2(r2, r3, r4, d):
    #test calculations
    r_set = 40.311
    r2 -= r_set
    r3 -= r_set
    r4 -= r_set
    # Calculate the position based on the given values
    r = (r2**2 + r3**2 - r4**2) / (2 * (r4 - r2 - r3))

    Y1 = (((r+r3)**2) + (d**2) - ((r+r2)**2)) / (2 * d)

    X1 = d - sqrt((r+r2)**2 - (Y1**2))

    #return X1, Y1
    return r, Y1, X1

#print(calculate_possition_2(87.321,68.007,103.078,100))


def calculate_possition(r2, r3, r4, d):
    r = (r2**2 + r3**2 - r4**2) / (2 * (r4 - r2 - r3))

    Y1 = (((r+r3)**2) + (d**2) - ((r+r2)**2)) / (2 * d)

    X1 = d - sqrt((r+r2)**2 - (Y1**2))

    return X1, Y1


def convert_time_to_mm(p1_p2, p1_p3, p1_p4,vMat=2270,Offset=0):
    scaling_faktor = (vMat + Offset) * 1000
    r3 = p1_p2 * scaling_faktor
    r4 = p1_p3 * scaling_faktor
    r2 = p1_p4 * scaling_faktor
    return r2, r3, r4