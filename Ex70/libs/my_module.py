from libs.utils import is_leap_year
def get_number_of_days(year, month):
    if month in (1,3,5,7,8,10,12):
        return 31
    elif month in (4,6,9,11):
        return 30
    elif month==2:
        if (is_leap_year(year)):
            return 29
        else:
            return 28