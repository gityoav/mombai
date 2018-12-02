from ordered_set import OrderedSet
import numpy as np
import pandas as pd
from mombai._decorators import try_false
from _collections_abc import dict_keys, dict_values
from copy import copy
import sys
version = sys.version_info


if version.major<3:
    def is_array(value):
        return isinstance(value, (list, tuple, range, np.ndarray))
else:
    def is_array(value):
        return isinstance(value, (list, tuple, range, np.ndarray, dict_keys))
    
def as_list(value):
    if value is None:
        return []
    elif is_array(value):
        return list(value)
    else:
        return [value]

def as_array(value):
    if value is None:
        return []
    elif is_array(value):
        return value
    else:
        return [value]

def as_ndarray(value):
    try:
        return np.array(as_list(value))
    except ValueError:
        return np.array(as_list(value), dtype='object')

def as_type(value):
    return value if isinstance(value, type) else type(value)

def _eq_attrs(x, y, attrs):
    for attr in attrs:
        if hasattr(x, attr) and not eq(getattr(x, attr), getattr(y, attr)):
            print(attr)
            return False
    return True

def eq(x, y):
    """
    A slightly better equality comparator
    >>> import numpy as np
    >>> import pandas as pd
    >>> import pytest
    
    >>> assert not np.nan == np.nan  ## Why?? 
    >>> assert eq(np.nan, np.nan)
    >>> assert eq(np.array([np.array([1,2]),2]), np.array([np.array([1,2]),2]))
    >>> assert eq(np.array([np.nan,2]),np.array([np.nan,2]))    
    >>> assert eq(dict(a = np.array([np.array([1,2]),2])) ,  dict(a = np.array([np.array([1,2]),2])))
    >>> assert eq(dict(a = np.array([np.array([1,np.nan]),np.nan])) ,  dict(a = np.array([np.array([1,np.nan]),np.nan])))
    >>> assert eq(np.array([np.array([1,2]),dict(a = np.array([np.array([1,2]),2]))]), np.array([np.array([1,2]),dict(a = np.array([np.array([1,2]),2]))]))
    
    >>> class FunnyDict(dict):
    >>>     pass
    >>> assert dict(a = 1) == FunnyDict(a=1)
    >>> assert not eq(dict(a = 1), FunnyDict(a=1))    
    >>> assert 1 == 1.0
    >>> assert eq(1, 1.0)
    >>> assert eq(x = pd.DataFrame([1,2]), y = pd.DataFrame([1,2]))
    >>> assert eq(pd.DataFrame([np.nan,2]), pd.DataFrame([np.nan,2]))
    >>> assert eq(pd.DataFrame([1,np.nan], columns = ['a']), pd.DataFrame([1,np.nan], columns = ['a']))
    >>> assert not eq(pd.DataFrame([1,np.nan], columns = ['a']), pd.DataFrame([1,np.nan], columns = ['b']))
    """
    if x is y:
        return True
    elif isinstance(x, (np.ndarray, tuple, list)):
        return type(x)==type(y) and len(x)==len(y) and _eq_attrs(x,y, ['__shape__']) and np.all(_veq(x,y))
    elif isinstance(x, (pd.Series, pd.DataFrame)):
        return type(x)==type(y) and _eq_attrs(x,y, attrs = ['__shape__', 'index', 'columns']) and np.all(_veq(x,y))
    elif isinstance(x, dict):
        if type(x) == type(y) and len(x)==len(y):
            xkey, xval = zip(*sorted(x.items()))
            ykey, yval = zip(*sorted(x.items()))
            return eq(xkey, ykey) and eq(np.array(xval, dtype='object'), np.array(yval, dtype='object'))
        else:
            return False
    elif isinstance(x, float) and np.isnan(x):
        return isinstance(y, float) and np.isnan(y)  
    else:
        res = x == y
        return np.all(res.__array__()) if hasattr(res, '__array__') else res

_veq = np.vectorize(eq)

class ordered_set(OrderedSet):
    """
    An ordered set but one that supports operations with non-sets:
    >>> assert ordered_set([1,2,3]) - 1 == ordered_set([2,3])
    >>> assert ordered_set([1,2,3]) + 4 == ordered_set([1,2,3,4])
    >>> assert ordered_set([1,2,3]) + [3,4] == ordered_set([1,2,3,4])
    >>> assert ordered_set([1,2,3]) & [3,4] == ordered_set([3])
    """
    @classmethod
    def cast(cls, other):
        if isinstance(other, cls):
            return other
        return ordered_set(as_list(other))
    def __str__(self):
        return list(self).__str__()
    def __repr__(self):
        return list(self).__repr__()
    def __add__(self, other):
        return self | ordered_set.cast(other)
    def __and__(self, other):
        return super(ordered_set, self).__and__(ordered_set.cast(other))
    def __sub__(self, other):
        return super(ordered_set,self).__sub__(ordered_set.cast(other))
    def __mod__(self, other):
        return self - (self & other)
    
class slist(list):
    """
    A list of unique items which behaves like an ordered set
    """
    def __init__(self, *args, **kwargs):
        super(slist, self).__init__(ordered_set(*args, **kwargs))
    def __add__(self, other):
        return slist(ordered_set(self) + other)
    def __and__(self, other):
        return slist(ordered_set(self) & other)
    def __or__(self, other):
        return slist(ordered_set(self) | other)
    def __sub__(self, other):
        return slist(ordered_set(self) - other)
    def __mod__(self, other):
        return slist(ordered_set(self) % other)


def _args_len(*values):
    lens = slist([len(value) for value in values]) - 1
    if len(lens)>1:
        raise ValueError('all values must have same length')
    return lens[0] if lens else 1
    
def args_len(*values):
    return _args_len(*[as_ndarray(value) for value in values])
    
def args_zip(*values):
    """
    This function is a safer version of zipping. 
    We insist that all elements have size 1 or the same length
    """
    values = [as_ndarray(value) for value in values]
    n = _args_len(*values)
    values = [np.concatenate([value]*n) if len(value)!=n else value for value in values]
    return zip(*values)

def args_to_list(args):
    """
    this is used to allow a function to take a zipped/unzipped parameters:
    >>> from operator import __add__
    >>> from functools import reduce
    >>> def func(*args):
    >>>     args = args_to_list(args)
    >>>     return reduce(__add__, args)
    >>> assert func(1,2,3) == func([1,2,3])
    """
    args = as_list(args)
    return args[0] if len(args)==1 and is_array(args[0]) else args


def args_to_dict(args):
    """
    returns a dict from a list, a single value or a dict.
    >>> assert args_to_dict(('a','b',dict(c='d'))) == dict(a='a',b='b',c='d')
    >>> assert args_to_dict([dict(c='d')]) == dict(c='d')
    >>> assert args_to_dict(dict(c='d')) == dict(c='d')
    >>> assert args_to_dict(['a','b',dict(c='d'), dict(e='f')]) == dict(a='a',b='b',c='d', e='f')
    >>> import pytest
    >>> with pytest.raises(ValueError):
    >>>     args_to_dict(['a','b',lambda c: c]) == dict(a='a',b='b',c='d', e='f')
    """
    args = args_to_list(args)
    res = dict()
    for arg in args:
        if isinstance(arg, dict):
            res.update(arg)
        else:
            if isinstance(arg, str):
                res[arg] = arg
            else:
                raise ValueError('cannot use a non-string %s in the list, it must be assigned a string name by making it into a dict'%arg)
    return res

def data_and_columns_to_dict(data=None, columns=None):
    """
    data is assumed to be a list of records (i.e. horizontal) rather than column inputs
    >>> data = [[1,2],[3,4],[5,6]]; columns = ['a','b']
    >>> assert list(data_and_columns_to_dict(data, columns)['a']) == [1,3,5]
    
    We can convert from pandas:
    >>> df = pd.DataFrame(data=data, columns = columns)
    >>> dfa = df.set_index('a')
    >>> assert list(data_and_columns_to_dict(df)['a']) == [1,3,5]
    >>> assert list(data_and_columns_to_dict(dfa)['a']) == [1,3,5]
    >>>
    >>> data = [['a','b'],[1,2],[3,4],[5,6]]; columns = None
    >>> assert list(data_and_columns_to_dict(data, columns)['a']) == [1,3,5]
    >>>
    >>> data = dict(a = [1,3,5], b = [2,4,6]); columns = None
    >>> assert data_and_columns_to_dict(data) == data
    >>> assert data_and_columns_to_dict(data.items()) == data
    >>> assert data_and_columns_to_dict(zip(data.keys(), data.values())) == data
    """
    if data is None and columns is None:
        return {}
    elif columns is not None:
        if isinstance(columns, str):
            return {columns : as_list(data)}
        else:
            return dict(zip(columns, np.asarray(data).T))
    else:
        if isinstance(data, str):
            data = pd.read_csv(data)
        if isinstance(data, pd.DataFrame):
            if data.index.name is not None:
                data = data.reset_index()
            return data.to_dict('list')
        if isinstance(data, list):
            if len(data) == 0:
                return {}
            elif min([isinstance(record, tuple) and len(record) == 2 for record in data]):
                return dict(data)
            else:
                return data_and_columns_to_dict(data[1:], data[0])
        else:
            return dict(data)


