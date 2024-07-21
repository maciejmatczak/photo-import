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

- import session handling
  - on each import, bound dates for each scenario should be saved
- flow:
  - after import data, save the current "boundaries" of last used import, so they would be reused automatically next time