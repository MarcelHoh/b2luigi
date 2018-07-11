import contextlib
import importlib

import itertools
import os
import collections
import sys

from b2luigi.core.settings import set_setting, get_setting


@contextlib.contextmanager
def remember_cwd():
    """Helper contextmanager to stay in the same cwd"""
    old_cwd = os.getcwd()
    try:
        yield
    finally:
        os.chdir(old_cwd)


def product_dict(**kwargs):
    """
    Cross-product the given parameters and return a list of dictionaries.

    Example:
    .. code-block:: python

        >>> list(product_dict(arg_1=[1, 2], arg_2=[3, 4]))
        [{"arg_1": 1, "arg_2": 3}, {"arg_1": 1, "arg_2": 4}, {"arg_1": 2, "arg_2": 3}, {"arg_1": 2, "arg_2": 3}]


    :param kwargs: Each keyword argument should be an iterable
    :return: A list of kwargs where each list of input keyword arguments is cross-multiplied with every other.
    """
    keys = kwargs.keys()
    vals = kwargs.values()
    for instance in itertools.product(*vals):
        yield dict(zip(keys, instance))


def fill_kwargs_with_lists(**kwargs):
    """
    Return the kwargs with each value mapped to [value] if not a list already.

    Example:
    .. code-block:: python

        >>> fill_kwargs_with_lists(arg_1=[1, 2], arg_2=3)
        {"arg_1": [1, 2], "arg_2": [3]}

    :param kwargs: The input keyword arguments
    :return: Same as kwargs, but each value mapped to a list if not a list already
    """
    return_kwargs = {}
    for key, value in kwargs.items():
        if value is None:
            value = []
        if not isinstance(value, collections.Iterable):
            value = [value]
        return_kwargs[key] = value

    return return_kwargs


def flatten_to_file_paths(inputs):
    """
    Take in a structure of something and replace each luigi target by its corresponding path.
    For dicts, it will replace the value as well as the key. The key will however only by the basename of the path.

    :param inputs: A dict or a luigi target
    :return: A dict with the keys replaced by the basename of the targets and the values by the full path
    """
    if not inputs:
        return None

    try:
        return inputs.path
    except AttributeError:
        pass

    if isinstance(inputs, dict):
        return {os.path.basename(flatten_to_file_paths(key)):
                    flatten_to_file_paths(value) for key, value in inputs.items()}
    else:
        return inputs


def flatten_to_dict(inputs):
    """
    Return a whatever input structure into a dictionary.
    If it is a dict already, return this.
    If is is an iterable of dict or dict-like objects, return the merged dictionary.
    All non-dict values will be turned into a dictionary with value -> {value: value}

    Example:
    .. code-block:: python

        >>> flatten_to_dict([{"a": 1, "b": 2}, {"c": 3}, "d"])
        {"a": 1, "b": 2, "c": 3, "d": "d"}

    :param inputs: The input structure
    :return: A dict constructed as described above.
    """
    inputs = _flatten(inputs)
    inputs = map(_to_dict, inputs)

    joined_dict = {}
    for i in inputs:
        joined_dict.update(**i)
    return joined_dict


def flatten_to_list_of_dicts(inputs):
    inputs = _flatten(inputs)
    inputs = map(_to_dict, inputs)

    joined_dict = collections.defaultdict(list)
    for i in inputs:
        for key, value in i.items():
            joined_dict[key].append(value)
    return joined_dict


def task_iterator(task):
    yield task
    for dep in task.deps():
        yield from task_iterator(dep)


def get_all_output_files_in_tree(root_module, key=None):
    if key:
        return get_all_output_files_in_tree(root_module)[key]

    all_output_files = collections.defaultdict(list)
    for task in task_iterator(root_module):
        output_dict = task.get_output_file_names()
        if not output_dict:
            continue

        for file_key, file_name in output_dict.items():
            all_output_files[file_key].append(dict(parameters=task.get_serialized_parameters(),
                                                   file_name=os.path.abspath(file_name)))

    return all_output_files


def filter_from_params(output_files, **kwargs):
    kwargs_list = fill_kwargs_with_lists(**kwargs)

    if not kwargs_list:
        return output_files

    file_names = set()

    for kwargs in product_dict(**kwargs_list):
        for output_dict in output_files:
            parameters = output_dict["parameters"]

            not_use = False
            for key, value in kwargs.items():
                if key in parameters and parameters[key] != value:
                    not_use = True
                    break

            if not_use:
                continue

            file_names.add(output_dict)

    return list(file_names)


def get_task_from_file(file_name, task_name, settings=None, **kwargs):
    with remember_cwd():
        os.chdir(os.path.dirname(file_name))
        spec = importlib.util.spec_from_file_location("module.name", os.path.basename(file_name))
        task_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(task_module)

        if settings:
            for key, value in settings.items():
                set_setting(key, value)
        m = getattr(task_module, task_name)(**kwargs)

        return m


def get_serialized_parameters(task):
    """Get a string-typed ordered dict of key=value for the significant parameters"""
    serialized_parameters = collections.OrderedDict()

    for key, parameter in task.get_params():
        if not parameter.significant:
            continue

        value = getattr(task, key)
        value = parameter.serialize(value)

        serialized_parameters[key] = value

    return serialized_parameters


def create_output_file_name(task, base_filename, create_folder=False, result_path=None):
    serialized_parameters = get_serialized_parameters(task)

    if not result_path:
        result_path = get_setting("result_path", ".")

    param_list = [f"{key}={value}" for key, value in serialized_parameters.items()]
    filename = os.path.join(result_path, *param_list, base_filename)

    if create_folder:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
    return filename


def get_log_files(task):
    filename = os.path.realpath(sys.argv[0])
    log_folder = get_setting("log_folder", default=os.path.join(os.path.dirname(filename), "logs"))
    stdout_file_name = create_output_file_name(task, task.get_task_family() + "_stdout", create_folder=True,
                                               result_path=log_folder)

    stderr_file_name = create_output_file_name(task, task.get_task_family() + "_stderr", create_folder=True,
                                               result_path=log_folder)

    return stdout_file_name, stderr_file_name


def _to_dict(d):
    if isinstance(d, dict):
        return d

    return {d: d}


def _flatten(struct):
    if isinstance(struct, dict) or isinstance(struct, str):
        return [struct]

    result = []
    try:
        iterator = iter(struct)
    except TypeError:
        return [struct]

    for f in iterator:
        result += _flatten(f)

    return result
