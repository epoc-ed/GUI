from pathlib import Path
from epoc import ConfigurationClient, auth_token, redis_host

# Connect to Redis
cfg = ConfigurationClient(redis_host(), token=auth_token())

# Load configuration from YAML (flush_db=True clears any existing data)
cfg.from_yaml(Path('epoc-config.yaml'), flush_db=True)

print("Redis database initialized successfully!")
print(cfg)