
# LevityDashboard

<a href="#getting-started" id=next-section>Getting Started</a>

The goal of LevityDash is to be a simple but extremely customizable dashboard.  This section will go over the basics of LevityDash and how to get started making your own dashboards.

## The Basics <!-- {docsify-ignore} -->

The key parts of LevityDash that are essential to understand are:

### Plugins <!-- {docsify-ignore} -->

LevityDash is designed to display data from multiple sources; these sources are called plugins.
Plugins are only used for pulling data from a source and providing it to the dashboard. 

More information can be found [here](/about/plugins.md) or by selecting the section in the sidebar.

### Dashboards <!-- {docsify-ignore} -->

Dashboards are the main configuration file for LevityDash.
Written in YAML, they are used to define the layout of the dashboard and what modules to use and how their panels are displayed.

More information can be found [here](/about/dashboard.md) or by selecting the section in the sidebar.

### Modules <!-- {docsify-ignore} -->

Modules, are the building blocks of a dashboard.  They represent the various ways to display information.

More information about modules can be found [here](about/modules.md) or by selecting the section in the sidebar.

### Panels <!-- {docsify-ignore} -->
Panels are instances of modules on the dashboard.  Panels can be resized and moved around the dashboard.  To remove a panel, right click on it and select 'Delete' or press the delete or backspace key when the panel is selected. More information can be found [here](/config/panels.md).


## Minor Features <!-- {docsify-ignore} -->
There are tons of other minor features already built in to LevityDash. Some of these features include:

[modules](/about/other-features.md ':include')

If you have any suggestions for new features, please feel free to open an issue on the [GitHub]()