In most cases, installing LevityDash is easy with pip:

```bash
pip install LevityDash
```

Or, for a more foolproof installation...

```bash
python3 -m pip install --upgrade --user LevityDash
```




However, there are a few dependencies (PySide2 and SciPy are the main issues) that can cause issues depending on the platform and CPU architecture.
This is generally the case for ARM devices, specifically AArch64 devices.
If any of the requirements fail to install with pip, you can try installing them manually with your package manager, otherwise, you can try building them from source.


## Using System Packages

Python packages are installed with the OS's package manager should be recognized automatically by pip.
If you are using a virtual environment, running some other obscure situation or the python packages are just not loading, you may need to include these packages manually.

To find the path where system python packages are installed, the following command will print all the directories that are named `site-packages`.
If you are looking for a specific package, you can use `'*/site-packages/<package>'` to find the directory for that package.

```shell
find / -type d -iwholename '*/site-packages' 2>&1 | grep -v 'Permission denied' >&2
```

Adding this path to your `PYTHONPATH` environment variable will allow python to find the package.
You will want to use 'site-packages' that is closest to the root of your filesystem.
Generally, it will start with `/usr`, `/lib`, or `/opt`.

>[!TIP]
> You can change the 'PySide2' to any other package you are having trouble with to find the path for that package.
> For example, if you are having trouble with the 'scipy' package, you would run:
> ```bash
> find / -type d -wholename '*/site-packages/scipy' 2>&1 | grep -v 'Permission denied' >&2
> ```


### Qt/PySide

If installing on Windows or macOS, Qt/Pyside should install automatically with pip.
With Linux, it depends on your distribution, window manager, desktop environment and, most importantly, your CPU architecture.

PySide2 does not have an ARM compatible module available in the PyPi repository, to fix this, you can either build the module yourself (See [here](https://github.com/piwheels/packages/issues/4#issuecomment-772058821) for more information),
use [piwheels.org](https://piwheels.org/) for non 64bit builds, or use your OS's package manager, which is recommended method.

Depending on your distro, you may be able to install PySide2 with your package manager.
If you are using a distro not listed below, you can try searching for "python-pyside6" in your package manager.

<!-- tabs:start -->

### **Debian**

```bash
sudo apt-get install python3-pyside6
```

### **Arch**

```bash
sudo pacman -S python-pyside6
```

### **Fedora**

```bash
sudo dnf install python3-pyside6
```

<!-- tabs:end -->

### SciPy

Like with PySide2, SciPy does not always install cleanly with pip on Linux depending on your CPU architecture.
ARM based systems may run into issues installing with pip, but typically it can be fixed by using the OS's package manager.

<!-- tabs:start -->

### **Debian**

```bash
sudo apt-get install python3-scipy
```

### **Arch**

```bash
sudo pacman -S python-scipy
```

### **Fedora**

```bash
sudo dnf install python3-scipy
```

<!-- tabs:end -->
