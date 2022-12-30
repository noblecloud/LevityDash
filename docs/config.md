# Configuring LevityDash

This section will cover the configuration options for LevityDash and the how to customise or make your own dashboards. 
There are two main types of configuration options: application/plugin and dashboard/panel. 
Currently, application/plugin configuration options use the ini format, while dashboard/panel configuration options use the YAML format.

## Location <!-- {docsify-ignore} -->

The location of the config folder is platform specific so the easiest way access it is by clicking the option in the File menu.

<!-- tabs:start -->

#### Platform Specific Config Locations  <!-- {docsify-ignore} -->

#### **Linux**

```bash
~/.local/share/LevityDash
```

#### **macOS**

```bash
~/Library/Application Support/LevityDash
```

#### **Windows**

```bash
%APPDATA%\LevityDash\LevityDash
```

<!-- tabs:end -->


<small>

?> **_NOTE:_**
LevityDash currently uses python's built in config parser and uses it's ini file format.
This will eventually be changed to TOML or YAML within the next few releases.
I am hoping to have an auto migration tool in place before the switch, but I can see the of the next few dev releases making the switch before the migration tool is ready.

</small>