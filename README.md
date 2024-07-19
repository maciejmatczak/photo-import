# photo-import

Small helper for photo import job.

## Example user config

```yaml
target_root: E:\workspace\photo-import\build\dump
include:
  - jpg
  - png
  - orf
  - mp4
  - rw2
exclude: []
scenarios:
  fz300:
    source: D:\_zrzut-zdjec\FZ300
```

## TODO

- add appdir based config
  - app config should point to scenario config
  - scenario config should exist somewhere else - easier to backup, etc.
- add data handling: app data?
- flow:
  - after import data, save the current "boundaries" of last used import, so they would be reused automatically next time