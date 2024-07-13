# photo-import

Small helper for photo import job.

## Design spec

- user configuration
- tool data
- supports multiple devices
- cli utility
- import flow
  - start
  - choose device
  - read all the files since last import (timestamp? exif?)
  - copy files (python copy? rclone?)
  - save timestamp of last copied foto

### Config

```yaml
target_root: /path/to/target/dump
file_formats:
  - jpg
  - orf
  - mp4
scenarios:
  Aparat:
    source: /source/path
```

### Data

```yaml
Aparat:
  last_photo_timestamp: xyz
```

