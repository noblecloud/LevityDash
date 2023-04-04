LevityDash's only requirement is Python 3.10 or newer.
There are many ways to install python that will be covered later, but for now, we will check what versions, if any, are already installed.

<small>

Python 3.11 is now Supported!.

</small>


## Checking Python Version

To check the version of python installed, run the following command in your terminal

<!-- tabs:start -->

#### Checking Python Version <!-- {docsify-ignore} -->

### **Windows**

Press "Win-R," type "cmd" and press "Enter" to open the command prompt.  If you have powershell installed, you can use that instead.

```shell
py -0
```

or to include paths of each python installation

```shell
py -0p
```

<small>Note: These commands are unique to Windows.  Python for windows includes a command for listing all installed versions</small>

### **macOS**

Terminal.app can be found in the `/Applications` folder.  If you have iTerm2 or another terminal emulator installed, you can use that instead.

```bash
python3 --version
```

### **Linux**

If you're on linux, you probably know how to open a terminal.  If you don't, you can use the "Search" feature in your desktop environment to find it.

```bash
python3 --version
```

<!-- tabs:end -->

If you have python installed, it should print the version number; if not, you will get an error message.

If the version of python is compatible, you can skip ahead to the next section [installing](/installing.md).


## Installing Python

### Python.org
The officially supported way is downloading directly from https://python.org.  However, this leaves the user managing multiple versions of Python and can be a huge hassle if you have other programs or scripts that require a version that is not supported by LevityDash.

### Pyenv
I've found [pyenv](https://github.com/pyenv/pyenv) to be the easiest way to install and manage versions of Python.
It makes installing new versions a breeze, has a builtin virtual environment manager, and allows you to specify versions of python for specific folders. 
RealPython.com has a great article about pyenv here: https://realpython.com/intro-to-pyenv/
and installation instructions for pyenv can be found here: https://github.com/pyenv/pyenv#installation

### Built-in Package Manager

#### Windows

Windows 10 comes with a built-in package manager called "Windows Package Manager."  It can be installed by running the following command in PowerShell:

```powershell
winget install Microsoft.Python.Python.3.11
```

Chocolatey is another package manager for Windows.  It can be installed by running the following command in PowerShell:

```powershell
choco install python
```


#### macOS

Homebrew is the most popular package manager for macOS.  It can be installed by running the following command in Terminal:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Once homebrew is installed, python can be installed by running the following command in Terminal:

```bash
brew install python@3.11
```

#### Linux

Linux distributions have a wide variety of package managers.  The most popular are apt, pacman, and dnf.  The following commands will install python 3.11 on each of these package managers:
<!-- tabs:start -->

### **Debian**

```bash
sudo apt-get install python3
```

<small>Note: This will install the latest version of Python 3, which will only be the case if you are on Debian Bookworm or Sid</small>

### **Arch**

```bash
sudo pacman -S python
```

### **Fedora**

```bash
sudo dnf install python3
```

<!-- tabs:end -->


If your distribution's package manager does not have Python 3.10 or newer, many times you can find community maintained packages for it.
If your package manager has a search feature, you can search for "python3.11" or "python3.11-dev" to find the package.
Additionally, your package manager may have a way to specify a specific version of a package to install.

### From Source <!-- {docsify-ignore-all} -->
If you are on a system that does not have a package manager, you can build python from source.  This is not recommended, but if you are determined, you can find instructions here:

<details id=quick-start>
<summary id="quick-start-expander">

Build instructions

</summary>

### Building Python from Source <!-- {docsify-ignore} -->

The following only works on Unix-like systems.

#### Install Build Dependencies
Install the following dependencies:

<!-- tabs:start -->

#### Dependencies <!-- {docsify-ignore} -->

##### **Debian**

```bash
sudo apt install build-essential zlib1g-dev libncurses5-dev libgdbm-devlibnss3-dev libssl-dev libreadline-dev libffi-dev wget git
```

##### **Arch**

```bash
sudo pacman -S base-devel zlib ncurses gdbm nss openssl readline libffi wget git
```

##### **Fedora**

```bash
sudo dnf install gcc zlib-devel bzip2 bzip2-devel readline-devel sqlite sqlite-devel openssl-devel tk-devel libffi-devel libuuid-devel xz-devel libffi-devel
```

<!-- tabs:end -->

#### Download the Source Code

```bash
MINOR=11
PATCH=9

wget https://www.python.org/ftp/python/3.$MINOR.$PATCH/Python-3.$MINOR.$PATCH.tar.xz
tar -xf Python-3.$MINOR.$PATCH.tar.xz
```

#### Build and Install

```bash
# Change to the directory where the source code was extracted
cd Python-3.$MINOR.$PATCH

# Configure the build
./configure --enable-optimizations

# Get the number of cores on your system or manually set it
CPU_CORES=$(nproc --all)

# Build and install
make -j $CPU_CORES
```

You can also install without overwriting the system python by running `make altinstall` instead of `make install`.
```bash
sudo make altinstall -j $CPU_CORES
```

</details>


### Other Methods
There are many other ways to install python, but I have not tested them.  If you have a method that works, please open an issue on the GitHub repo and I will add it to this page.