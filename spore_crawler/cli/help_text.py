"""
help_text.py - All CLI help text, command descriptions, aliases, usage examples.

Depends on: None (leaf module)
Used by: cli/__init__
"""
HELP_TEXT = """
USAGE:
  Just type whatever command you need!
  Read help for each command by adding "--help or -h" at the end.

COMMANDS:
  stats                 Show Sporepedia site statistics
  crawl                 Download creations from Sporepedia
  sporecast             Download sporecasts from users
  search                Search for sporecasts by keyword (requires login)
  browse                Browse Sporepedia by keyword (no login needed)
  list                  List sporecasts for a user
  login                 Authenticate with Spore (EA SSO)
  convert-sql           Export database to readable plain text
  config                Manage configuration
  clean                 Delete databases and downloads
  bean                  BEAN
  bean_test             BEAN

HOTKEYS (during crawl/sporecast/search/browse):
  P - Pause crawling
  R - Resume crawling
  X - Stop crawling (saves progress)
"""

COMMAND_HELP = {
    'stats': """
stats - Show Sporepedia site statistics

USAGE:
  stats

Displays total uploads, total users, and today's activity.
No options available.
""",
    'crawl': """
crawl - Download creations from Sporepedia

USAGE:
  crawl [options]

OPTIONS:
  -sort / --sort <list>    Comma-separated sort methods (default: from config)
  -views / --views <list>  Alias for --sort (deprecated)
  -types / --types <list>  Comma-separated asset types (default: from config)
  -subtypes / --subtypes <list>  Comma-separated subtypes to filter
                            Creatures: Animal, Tribal, Civ, Space, Captain
                            Buildings: City Hall, House, Factory, Entertainment
                            Vehicles: Military Land/Water/Air, Economic Land/Water/Air,
                                      Religious Land/Water/Air, Colony Land/Water/Air, Spaceships
                            Adventures: Attack, Collect, Defend, Explore, Puzzle,
                                        Quest, Socialize, Story, Template, No Genre
  -mp / --max-pages <n>    Max pages to crawl (0 = unlimited)
  -a / --amount <n>        Stop after downloading N PNGs (per category)
  -s / --size <n>          Stop after downloading N megabytes (per category)
  -f / --forcestop         Stop ALL categories when limit is hit

  BROWSE DATABASE:
  -db / --db               Download assets from search_sporecast.db (populated by 'browse')

  DATABASE CHUNKS:
  --save-chunk <name>      Save database to a chunk file after crawl
  --load-chunk <path>      Load a database chunk before crawling
  --skipcheck              Skip verification when loading chunks (faster)
  --list-chunks            List available database chunks

  NOTE: --max-pages, --amount, and --size cannot be combined.
        Use only one limit at a time.

  IMPORTANT: At least one limit argument is required to prevent infinite
  crawling. Use 0 for unlimited download.
  Exception: --db mode downloads all browsed assets.

  By default, limits are per category. Example:
    crawl --size 20 --types CREATURE,BUILDING
    Downloads 20 MB of CREATURES, then 20 MB of BUILDINGS.

  With --forcestop, hitting the limit stops everything:
    crawl --size 20 --types CREATURE,BUILDING --forcestop
    Downloads 20 MB of CREATURES, then stops entirely.

  Single-dash args work: -sort NEWEST, -mp 10, -a 100, -s 1024, -db

  HOTKEYS (during crawl):
    P - Pause crawling
    R - Resume crawling
    X - Stop crawling (saves progress)

SIZE HINT (--size uses megabytes):
  To get gigabytes, multiply by 1024:
    1 GB   =   1024 MB
    5 GB   =   5120 MB
    10 GB  =  10240 MB
    30 GB  =  30720 MB
    50 GB  =  51200 MB

  Example: --size 5120 will stop after 5 GB

SORT METHODS:
  NEWEST           Recently uploaded
  TOP_RATED        Most Popular (all time)
  TOP_RATED_NEW    Most Popular New (recent high-rated)
  FEATURED         Featured by Maxis
  MAXIS_MADE       Official Maxis creations
  RANDOM           Random selection
  CUTE_AND_CREEPY  Creepy & Cute pack

ASSET TYPES:
  CREATURE, BUILDING, VEHICLE, ADVENTURE, UFO

DATABASE CHUNKS:
  Database chunks allow you to save and load database state.
  Useful for:
  - Backing up your download history
  - Sharing database state between machines
  - Loading external databases (e.g., from a 50GB archive download)

  Example workflow:
    1. Download content: crawl --size 5000 --save-chunk backup1
    2. Later, load external DB: crawl --load-chunk /path/to/other.db --skipcheck
    3. List chunks: crawl --list-chunks

EXAMPLES:
  crawl --size 1024         # Download 1 GB
  crawl -amount 1000        # Download 1000 PNGs (single dash)
  crawl --max-pages 50      # Crawl 50 pages
  crawl -a 0                # Unlimited download (single dash shorthand)
  crawl --views NEWEST --types CREATURE --amount 100
  crawl -size 5120 -f       # 5 GB with forcestop (single dash shorthand)
  crawl --save-chunk backup_20260620
  crawl --load-chunk ./db_chunks/backup1.db
  crawl --load-chunk ./other.db --skipcheck
  crawl --list-chunks
""",
    'sporecast': """
sporecast - Download sporecasts

USAGE:
  sporecast [options]

SOURCES:
  -u / --username <name>  Find sporecasts by creator name via DWR (requires login)
  -id / --id <id>         Download a specific sporecast by ID (no login needed)
  -all / --all            Enumerate all platform sporecasts then download (requires login)
  -db / --db              Download sporecasts from search_sporepedia.db or search_sporecast.db
  -temp / --temp          Download sporecasts from sporecasts_temp.txt (populated by 'search')
  -k / --key <keyword>    Search and download sporecasts by keyword (requires login)

AUTHENTICATION:
  --username, --all, and --key require EA SSO login via DWR to discover sporecasts.
  Credentials from 'login --new' or interactive prompt.
  Asset downloads use the public REST API (no login needed after discovery).

OPTIONS:
  -s / --size <n>         Stop after downloading N megabytes (finishes current sporecast)
  -a / --amount <n>       Stop after downloading N PNGs total (finishes current sporecast)
  -mp / --max-pages <n>   Stop after processing N sporecasts
  -sort / --sort <list>   Comma-separated sort methods for sporecast list
  -f / --forcestop        Stop ALL when limit is hit
  --save-chunk <name>     Save database to a chunk file after download
  --load-chunk <path>     Load a database chunk before downloading

  NOTE: --max-pages, --amount, and --size cannot be combined.
        Use only one limit at a time.

  IMPORTANT: At least one limit argument is required to prevent infinite
  downloading. Use 0 for unlimited download.

When limit is reached mid-sporecast, the current sporecast is fully downloaded
before stopping. This ensures you always have complete sporecast folders.

  Single-dash args work: -temp, -all, -k nemo, -s 4, -a 100

  HOTKEYS (during sporecast):
    P - Pause crawling
    R - Resume crawling
    X - Stop crawling (saves progress)

EXAMPLES:
  sporecast --username MaxisMichael    # Fetch + download user's sporecasts
  sporecast -id 500111970026           # Download single sporecast (single dash)
  sporecast --all                      # Enumerate ALL + download (~513k THEME)
  sporecast --db                       # Download from search database
  sporecast --temp                     # Download from temp file
  sporecast -k nemo -s 0               # Search + download sporecasts matching "nemo"
  sporecast --temp --size 4            # Download 4 MB, finish current sporecast
  sporecast -temp -amount 100          # Download 100 PNGs (single dash shorthand)
  sporecast --temp --max-pages 10      # Process 10 sporecasts
  sporecast --temp --amount 0          # Unlimited download
  sporecast --temp --size 5120 --forcestop
  sporecast --temp --save-chunk backup_sporecasts
  sporecast --temp --load-chunk ./db_chunks/backup.db
""",
    'search': """
search - Search for sporecasts by keyword or enumerate all

USAGE:
  search <terms...> [options]
  search --all [options]

OPTIONS:
  -all / --all            Enumerate ALL sporecasts (requires login, ~513k THEME sporecasts)
  -m / --max <n>          Max results per search term (0 = unlimited, default: 0)
  -f / --fields <list>    Comma-separated fields to search (default: from config)

SEARCH FIELDS (for --fields):
  title                 Sporecast Name
  author                Creator Name
  tags                  Tags
  subtitle              Description
  all                   Search all fields (same as leaving --fields empty)

Searches DWR API for sporecasts matching keywords.
By default, searches ALL fields (title, author, tags, description).
Use --fields to limit which fields are searched.

With --all, uses authenticated DWR to enumerate every sporecast on the platform.
Results saved to search_sporepedia.db and sporecasts_temp.txt.

Authentication (--all):
  Requires EA SSO login. Credentials from config or interactive prompt.
  Run 'login' first to authenticate.

  Single-dash args work: -all, -m 100, -f title

  HOTKEYS (during search):
    P - Pause crawling
    R - Resume crawling
    X - Stop crawling (saves progress)

Try these terms:
  creature, building, vehicle, adventure, maxis, pack, set,
  best, cool, funny, space, tribal, civ, city, house, military, economic

EXAMPLES:
  search creature                  # Search all fields for "creature"
  search pop                       # Search all fields for "pop"
  search pop -f title              # Search only sporecast names (single dash)
  search pop --fields author       # Search only creator names
  search pop --fields title,tags   # Search names and tags
  search building vehicle -m 200   # Search with max results (single dash)
  search cool best funny
  search --all                     # Enumerate all ~513k sporecasts
  search --all -m 0                # Same, unlimited (single dash)
""",
    'browse': """
browse - Browse Sporepedia creations (no login required)

USAGE:
  browse <creation_types...> [options]
  browse --all [options]

At least one creation type or --all is required. Without arguments, help is shown.

CREATION TYPES:
  creature / creatures       Browse creature creations
  building / buildings       Browse building creations
  vehicle / vehicles         Browse vehicle creations
  adventure / adventures     Browse adventure creations

OPTIONS:
  -all / --all              Browse all creation types
  -t / --type <list>        Comma-separated creation types (default: from config)
  -fi / --filter <method>   Filter method (default: newest)
  -m / --max <n>            Max results per type (0 = unlimited)
  -sub / --subtypes <list>  Comma-separated subtypes to filter

FILTERS (for --filter):
  newest                    Recently uploaded (default)
  highly_rated              Top rated of all time
  recent_highly_rated       Top rated recent creations
  featured                  Featured by Maxis
  all                       Random selection (slow)

SUBTYPES (for --subtypes):
  Creatures:  Animal, Tribal, Civ, Space, Captain
  Buildings:  City Hall, House, Factory, Entertainment
  Vehicles:   Military Land/Water/Air, Economic Land/Water/Air,
              Religious Land/Water/Air, Colony Land/Water/Air, Spaceships
  Adventures: Attack, Collect, Defend, Explore, Puzzle,
              Quest, Socialize, Story, Template, No Genre

Browses the Sporepedia REST API for creations.
No authentication required (uses public REST endpoint).
Results saved to search_sporecast.db.

Use 'sporecast --db' to download sporecasts from browsed results.
Use 'convert-sql browse' to export browsed data to text.

  Single-dash args work: -m 100, -t creature, -fi newest, -all, -help

  HOTKEYS (during browse):
    P - Pause browsing
    R - Resume browsing
    X - Stop browsing

EXAMPLES:
  browse creature                    # Browse creatures only
  browse building vehicle            # Browse buildings and vehicles
  browse --all                       # Browse all creation types
  browse creature -fi highly_rated   # Browse top-rated creatures
  browse adventure -fi featured      # Browse featured adventures
  browse creature -subtypes Animal,Tribal  # Filter by subtype
  browse -m 500 -all                 # Limit to 500 results, all types
  browse creature -fi newest -m 1000 # 1000 newest creatures
  browse -t creature -fi recent_highly_rated -subtypes Space
  browse -help                       # Show this help
""",
    'list': """
list - List sporecasts for a user (requires login)

USAGE:
  list <username> [options]

Lists all sporecasts associated with a username via DWR search.
Requires EA SSO authentication (run 'login' first).

OPTIONS:
  -f / --fields <list>  Comma-separated fields to search (default: author)

SEARCH FIELDS (for --fields):
  title                 Sporecast Name
  author                Creator Name
  tags                  Tags
  subtitle              Description
  all                   Search all fields

By default, searches by Creator Name (author).
Use --fields to search by other fields like title, tags, or description.

Single-dash args work: -f title

EXAMPLES:
  list MaxisMichael
  list LansRu -f title     # Search by sporecast name (single dash)
  list LansRu --fields all  # Search all fields
""",
    'login': """
login - Authenticate with Spore via EA SSO

USAGE:
  login [options]

OPTIONS:
  --new           Prompt for new email/password and save to credentials.json
  -d / --del      Delete saved credentials.json
  --rem           Alias for --del
  --delete        Alias for --del
  --remove        Alias for --del

Without options, uses saved credentials from credentials.json.
On failure, loops and prompts for credentials again.

Required for sporecast enumeration (listSporecastsDWR DWR method).

Single-dash args work: -d, -new

EXAMPLES:
  login              # Login with saved credentials
  login --new        # Enter new credentials
  login -d           # Delete saved credentials (single dash)
""",
    'convert-sql': """
convert-sql - Export database to readable plain text

USAGE:
  convert-sql <type>

TYPES:
  crawler / sporepedia    Export sporepedia.db (downloaded assets)
  search                  Export search_sporepedia.db (search tracking)
  browse                  Export search_sporecast.db (browse results)
  sporecast               Export sporecasts.db (sporecast downloads)
  all                     Export all four databases

Output saved as .txt file next to the database.

Shorthands: sc/sp/cv/sql/convert/export

EXAMPLES:
  convert-sql crawler
  convert-sql search
  convert-sql browse
  convert-sql sporecast
  convert-sql all
  sc all                  # Shorthand
""",
    'config': """
config - Manage configuration

USAGE:
  config <action> [options]

ACTIONS:
  -s / show            Show current configuration
  -v / validate        Validate configuration file
  -pre / presets       List available presets
  -ap / apply <preset> Apply a preset configuration
  -r / reset           Reset to default configuration
  -se / set <key> <value>  Set a config value
  -g / get <key>       Get a config value

Single-dash args work: -s, -v, -r, -se key val, -g key

EXAMPLES:
  config show
  config validate
  config presets
  config apply quick
  config reset
  config -se crawler.requests_per_second 2.0   # Single dash
  config -g crawler.requests_per_second        # Single dash

ENVIRONMENT OVERRIDES:
  Config values can be overridden by environment variables:
  SPORE_CRAWLER_CRAWLER_REQUESTS_PER_SECOND=2.0
  SPORE_CRAWLER_OUTPUT_DOWNLOAD_FOLDER=/tmp/downloads
  SPORE_CRAWLER_DATABASE_PATH=/tmp/sporepedia.db
  SPORE_CRAWLER_LOGGING_LEVEL=DEBUG
""",
    'clean': """
clean - Delete databases, downloads, and other tracked files

USAGE:
  clean

Deletes files based on config['clean'] settings:
  databases:      .db files (sporepedia.db, search_sporepedia.db, sporecasts.db, search_sporecast.db)
  downloads:      downloads/ folder (all downloaded PNGs)
  chunks:         db_chunks/ folder (database backups)
  config_yaml:    config.yaml
  crawler_log:    crawler.log
  credentials:    credentials.json
  database_txt:   converted .txt export files
  test_downloads: test_downloads/ folder

By default, only databases, downloads, and chunks are cleaned.
Edit config.yaml 'clean' section to enable/disable each category.

Shorthands: clear/purge

EXAMPLES:
  clean
""",
    'bean': """
bean - BEAN

USAGE:
  bean

Clears screen and displays success ASCII art.
Always available, no config required.
""",
    'bean_test': """
bean_test - BEAN

USAGE:
  bean_test

REQUIRES:
  bean_test: true in config.yaml

Tests database, API, crawl, and metadata functionality with safe settings.
Login is tested first (credentials requested if not saved).
Shows success/failure ASCII art.
""",
}

COMMAND_ALIASES = {
    # crawl aliases
    'sporepedia': 'crawl',
    'creations': 'crawl',
    'download': 'crawl',
    'dw': 'crawl',
    # sporecast aliases
    'cast': 'sporecast',
    'sporecasts': 'sporecast',
    # search aliases
    'find': 'search',
    'lookup': 'search',
    'look': 'search',
    'analyze': 'search',
    'query': 'search',
    # browse aliases
    'explore': 'browse',
    'b': 'browse',
    'br': 'browse',
    # list aliases
    'ls': 'list',
    'lst': 'list',
    'users': 'list',
    # login aliases
    'auth': 'login',
    'signin': 'login',
    # convert-sql aliases
    'sc': 'convert-sql',
    'sp': 'convert-sql',
    'convert': 'convert-sql',
    'export': 'convert-sql',
    'sql': 'convert-sql',
    'cv': 'convert-sql',
    # config aliases
    'cfg': 'config',
    'configuration': 'config',
    'settings': 'config',
    'setup': 'config',
    # clean aliases
    'clear': 'clean',
    'purge': 'clean',
    # bean aliases
    'beans': 'bean',
    'bean-test': 'bean_test',
}

# Argument aliases for crawl command
CRAWL_ARG_ALIASES = {
    '--mp': '--max-pages',
    '--p': '--max-pages',
    '--a': '--amount',
    '--files': '--amount',
    '--s': '--size',
    '--mb': '--size',
    '--fs': '--forcestop',
    '--f': '--forcestop',
}

# Argument aliases for sporecast command
SPORECAST_ARG_ALIASES = {
    '--mp': '--max-pages',
    '--p': '--max-pages',
    '--a': '--amount',
    '--files': '--amount',
    '--s': '--size',
    '--mb': '--size',
    '--fs': '--forcestop',
    '--f': '--forcestop',
    '-k': '--key',
}

# Argument aliases for search command
SEARCH_ARG_ALIASES = {
    '--a': '--all',
    '--m': '--max',
    '--f': '--fields',
    '--fl': '--fields',
}

# Argument aliases for browse command
BROWSE_ARG_ALIASES = {
    '--m': '--max',
    '--a': '--all',
    '--t': '--type',
    '--fi': '--filter',
    '--sub': '--subtypes',
}

# Argument aliases for convert-sql command
CONVERT_SQL_ARG_ALIASES = {
    '--sp': 'crawler',
    '--sc': 'crawler',
    '--sporepedia': 'crawler',
    '--s': 'search',
    '--se': 'search',
    '--src': 'search',
    '--cast': 'sporecast',
    '--sporecasts': 'sporecast',
    '--a': 'all',
    '--global': 'all',
}

# Argument aliases for config command
CONFIG_ARG_ALIASES = {
    '--s': 'show',
    '--v': 'validate',
    '--check': 'validate',
    '--chk': 'validate',
    '--pre': 'presets',
    '--sets': 'presets',
    '--ap': 'apply',
    '--confirm': 'apply',
    '--rs': 'reset',
    '--r': 'reset',
    '--se': 'set',
    '--g': 'get',
}

ALL_COMMANDS = list(COMMAND_HELP.keys())
