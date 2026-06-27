"""
config_cmd.py - `config` command: show/validate/presets/apply/reset/set/get.

Depends on: cli/commands/_common (get_app_dir), cli/config (validate, presets, etc.)
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - (apply/reset/set) Writes config.yaml to disk
"""
import json
import logging

import yaml

from spore_crawler.cli.commands._common import get_app_dir

log = logging.getLogger(__name__)


async def cmd_config(config: dict, action: str, args: list):
    """Handle config command actions."""
    from spore_crawler.cli.config import validate_config, get_config_presets, merge_defaults, DEFAULT_CONFIG_YAML

    log.info('Command: config, action=%s, args=%s', action, args)

    if action == 'show':
        print('Current configuration:')
        print(' ')
        print(json.dumps(config, indent=2, default=str))
        print('============================================================')
        return True

    if action == 'validate':
        print('Validating configuration...')
        errors = validate_config(config)
        if errors:
            print('Validation errors:')
            for error in errors:
                print(f'  - {error}')
            return False
        else:
            print('Configuration is valid!')
            return True

    if action == 'presets':
        presets = get_config_presets()
        print('Available presets:')
        print('============================================================')
        for name, preset in presets.items():
            print(f"\n  {name.upper()}:")
            print(f"    requests_per_second: {preset['crawler']['requests_per_second']}")
            print(f"    request_timeout: {preset['crawler']['request_timeout']}s")
            print(f"    page_size: {preset['crawler']['page_size']}")
            print(f"    sort_method: {', '.join(preset['crawler']['sort_method'])}")
            print(f"    asset_types: {', '.join(preset['crawler']['asset_types'])}")
            print(f"    logging_level: {preset['logging']['level']}")
        print('\n============================================================')
        print('Use: config apply <preset_name>')
        return True

    if action == 'apply':
        if not args:
            print('Error: Please specify a preset name')
            print('Use: config presets')
            return False

        preset_name = args[0].lower()
        presets = get_config_presets()

        if preset_name not in presets:
            print(f"Error: Unknown preset '{preset_name}'")
            print(f"Available presets: {', '.join(presets.keys())}")
            return False

        log.info("Config apply: applying preset '%s'", preset_name)

        config_path = get_app_dir() / 'config.yaml'

        if not config_path.exists():
            log.warning('Config file not found: %s', config_path)
            print(f"Config not found: {config_path}")
            return False

        with open(config_path, encoding='utf-8') as f:
            current_config = yaml.safe_load(f) or {}

        preset = presets[preset_name]
        merged = merge_defaults(preset, current_config)

        log.info('Config apply: preset=%s, rps=%.1f, timeout=%ds, page_size=%d, max_concurrent=%d',
                 preset_name, preset['crawler']['requests_per_second'],
                 preset['crawler']['request_timeout'],
                 preset['crawler']['page_size'],
                 preset['crawler'].get('max_concurrent_downloads', 5))

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(merged, f, default_flow_style=False, allow_unicode=True)

        log.info('Config apply: wrote %s', config_path)
        print(f"Applied preset '{preset_name}' to config.yaml")
        print('Changes will take effect on next command.')
        return True

    if action == 'reset':
        config_path = get_app_dir() / 'config.yaml'

        if not config_path.exists():
            log.warning('Config file not found: %s', config_path)
            print(f"Config not found: {config_path}")
            return False

        log.info('Config reset: writing default config to %s', config_path)

        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(DEFAULT_CONFIG_YAML)

        log.info('Config reset: complete')
        print('Reset config.yaml to defaults')
        print('Changes will take effect on next command.')
        return True

    if action == 'set':
        if not args or len(args) < 2:
            print('Error: Please specify key and value')
            print('Use: config set <key> <value>')
            return False

        key_path = args[0]
        value_str = args[1]

        log.info('Config set: key=%s, value=%s', key_path, value_str)

        parts = key_path.split('.')

        config_path = get_app_dir() / 'config.yaml'
        if not config_path.exists():
            print(f"Config not found: {config_path}")
            return False

        with open(config_path, encoding='utf-8') as f:
            current_config = yaml.safe_load(f) or {}

        if len(parts) == 1:
            key = parts[0]
            if key in current_config:
                current_type = type(current_config[key])
                if current_type == bool:
                    current_config[key] = value_str.lower() in ('true', '1', 'yes', 'on')
                elif current_type == int:
                    current_config[key] = int(value_str)
                elif current_type == float:
                    current_config[key] = float(value_str)
                else:
                    current_config[key] = value_str
            else:
                current_config[key] = value_str
        elif len(parts) == 2:
            section, key = parts
            if section not in current_config:
                current_config[section] = {}
            target = current_config[section]
            if key in target:
                current_type = type(target[key])
                if current_type == bool:
                    target[key] = value_str.lower() in ('true', '1', 'yes', 'on')
                elif current_type == int:
                    target[key] = int(value_str)
                elif current_type == float:
                    target[key] = float(value_str)
                else:
                    target[key] = value_str
            else:
                target[key] = value_str
        elif len(parts) == 3:
            section, subsection, key = parts
            if section not in current_config:
                current_config[section] = {}
            if subsection not in current_config[section]:
                current_config[section][subsection] = {}
            target = current_config[section][subsection]
            if key in target:
                current_type = type(target[key])
                if current_type == bool:
                    target[key] = value_str.lower() in ('true', '1', 'yes', 'on')
                elif current_type == int:
                    target[key] = int(value_str)
                elif current_type == float:
                    target[key] = float(value_str)
                else:
                    target[key] = value_str
            else:
                target[key] = value_str
        else:
            print('Error: Invalid key format')
            print('Use: config set <key> <value>')
            print('Examples:')
            print('  config set output.download_folder ./downloads')
            print('  config set crawler.requests_per_second 2.0')
            return False

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(current_config, f, default_flow_style=False, allow_unicode=True)

        log.info('Config set: wrote %s = %s to %s', key_path, value_str, config_path)
        print(f"Set {key_path} = {value_str}")
        print('Changes will take effect on next command.')
        return True

    if action == 'get':
        if not args:
            print('Error: Please specify a key')
            print('Use: config get <key>')
            return False

        key_path = args[0]
        parts = key_path.split('.')

        value = config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                log.info('Config get: key not found: %s', key_path)
                print(f"Key not found: {key_path}")
                return False

        log.info('Config get: %s = %s', key_path, value)
        print(f"{key_path} = {value}")
        return True

    print(f"Unknown action: {action}")
    print('Available actions: show, validate, presets, apply, reset, set, get')
    return False
