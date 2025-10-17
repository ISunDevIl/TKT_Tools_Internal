# tools/__init__.py
import pkgutil
import importlib

def load_tools():
    """Tự động load tất cả các class tool trong thư mục tools"""
    tools = {}
    package = __name__

    for loader, module_name, is_pkg in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{package}.{module_name}")

        # Giả sử mỗi tool đều có 1 class chính trùng tên file (viết PascalCase)
        class_name = ''.join([part.capitalize() for part in module_name.split('_')])
        if hasattr(module, class_name):
            tools[module_name] = getattr(module, class_name)

    return tools