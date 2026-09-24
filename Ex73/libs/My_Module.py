from math import sqrt

def quadratic_equation(a,b,c):
    if a == 0:
        #bx+c=0
        if b == 0 and c ==0:
            print("Infinite solutions")
        elif b==0 and c !=0:
            return ("No solutions")
        else:
            x=-c/b
            return ("Solution x=",x)
    else:
        delta=b**2-4*a*c
        if delta <0 :
            return ("No solutions")
        elif delta ==0:
            x=-b/(2*a)
            return ("Double solutions x1=x2=",x)
        else:
            x1=(-b-sqrt(delta))/(2*a)
            x2=(-b+sqrt(delta))/(2*a)
            return ("x1=",x1, "x2=",x2)
