Hey everyone, Happy Holidays!

I'm back with a very long on overdue update!

I've still got quite a bit of cleaning up with the UI/UX, documentation to write, and a few of bugs to address before I can release it, but I wanted to get feedback on the current progress. 
I believe I have addressed all the issues mentioned previously.

There is one major breaking change, dashboard layouts from previous versions may not be compatible.
The schema for dashboard configuration is not finalized, so this could end up being a continuing issue until it is.
I have some ideas of ways to make it less of an issue and make loading/saving significantly faster, but it might not get incorporated right away.

Finally, I stepped away from the project for a little while, so I am sure there are other changes that I've since forgotten.
I will continue to add them here as I remember or rediscover any important missing changes.

You can find the most up-to-date version of the documentation here: https://docs.levityda.sh/

The full changelog along with experimental compiled releases can be found here: https://github.com/noblecloud/LevityDash/releases/tag/v0.2.0b1

I have not published it to PyPi yet, but you can download the pre-release with pip by using the `--extra-index-url` flag:

```bash
python3.10 -m pip install --user --upgarde --extra-index-url https://repo.levelityda.sh/ LevityDash
```

Once again, I look forward to hearing everyone's thoughts!

Neal

---

### Text

First and foremost, Text, should be more consistently sized.
Text Labels can be configured with 'matching groups'; when a label is assigned a group, 
it will automatically be adjusted to be consistent with the rest of the items in the group.  
To prevent sizing from being too restrictive, by default, subgroups are created based on label size and proximity, 
but it can also be set to have a consistent size for all items.

The default font weights have been reduced.  
On top of the weight reduction, the default title font has was changed from Nunito to Roboto.  
Hopefully the font weight reduction and purposeful font variation helps with the visual density and readability.

There are a few other changes related to Text, but I'll leave that for the change log below.

### Borders

Basic border support has been added.  
The current config options for borders are: `edges`, `weight`, `color`, `length`, `offset`, and `opacity`.  
More options will be added over time, such as `dash-pattern` and individually styled edges.

### Stacks

For easier consistency and faster dashboard creation, Stack grouping support has been added.  
Items in a stack are automatically evenly sized unless otherwise specified.  
Before, everything had to be laid out by hand either in the dashboard config file, 
which made major changes tedious, or through the UI, which made major changes difficult to keep consistent.  
This feature was something I had already been working on, but it was not in good enough state to be included in the last release.  
Stacks are currently their own item group, I don't foresee this being the case forever, but it is the best way to implement them for now.  
Eventually, I would like to have 'stack' as a layout option for any item group along with 'grid' and 'freeform'.

### Physical Sizes

Physical size support has been to most size config options. 
Rather than pixels or percentages, sizes can be specified in metric or imperial lengths, e.g. `in`, `cm`, `mm`.

## What's Next

The next two areas of focus for the project will be adding more display types, and improving the plugin system. 
The gauge display module is nearly done, so it will probably be the first update but the plugin system improvements will most likely be spread across multiple updates.

### Other Notes

Many bugs have been fixed, but I'm sure there are still some lurking around.  
If you find any, please let me know or submit an [issue](https://github.com/noblecloud/LevityDash/issues/new?labels=help+wanted,bug&title=Short%20Description%20of%20the%20bug&body=Please%20list%20the%20steps%20to%20recreate%20the%20bug%20or%20describe%20the%20problem) on GitHub.

A few of the config options have been renamed for consistency and clarity.  
As a result, dashboard files created with previous versions may be incompatible with this version.

I am also in the process of slowly refactoring the codebase to be PEP 8 compliant, 
so if you notice some options are camelCase and others are snake_case, that is why.

Lastly, LevityDash is intended to be more than just a weather dashboard, 
I would love suggestions for other data sources and display methods.
I am hoping to have at least have a system stats plugin, and gauges by the next release.

## TLDR Change Log:

- New Modules
  - Mini-Graph
  - Stack
  - Titled Group
- Better text size handling
- Text styling support (experimental)
- Colors can now be specified with a hex string, a sequence of rgb/rgba values, or by web color name
- Icon/glyph support
- Metric and Imperial size support for MOST size options
- Shared/Cascading Attributes
- Borders
- Unit conversion
- Removed qasync dependency
- Significantly better multithreading due to removal of qasync
- Many under-the-hood improvements
- Popover details for graphs
- Significantly faster peak calculation (around 10x)
- History time-series changes are now announced/updated