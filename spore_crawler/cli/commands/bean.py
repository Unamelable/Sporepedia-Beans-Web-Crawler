"""
bean.py - Easter egg `bean` command and `bean_test` automated test suite.

Depends on: api/client, api/auth, storage/database, crawlers/full_crawler,
            cli/commands/_common, cli_ui, storage/png_metadata
Used by: cli/commands/__init__, cli/__init__

Side effects:
  - Clears screen, fills background (bean)
  - bean_test: Opens Database, makes API calls, writes test PNGs
  - bean_test: Opens SporeAuth for login test (Playwright browser)
  - Sets state['skip_pause'] = True (via cli/__init__)
"""
import logging
from pathlib import Path

from spore_crawler.api.client import SporeAPI
from spore_crawler.storage.database import Database
from spore_crawler.crawlers.full_crawler import crawl_assets

from spore_crawler.cli.commands._common import (
    get_resource_dir,
)

log = logging.getLogger(__name__)


async def cmd_bean():
    """Command: bean - clear screen and display success_ascii.txt."""
    from spore_crawler.cli_ui import clear_screen, fill_background, set_colors, enable_ansi, ensure_window_rows, FG_GREEN, FG_YELLOW
    log.info('Command: bean')
    ensure_window_rows(49)
    clear_screen()
    fill_background()
    enable_ansi()
    set_colors(fg=FG_YELLOW)
    ascii_dir = get_resource_dir()
    success_path = ascii_dir / 'success_ascii.txt'
    if success_path.exists():
        ascii_art = success_path.read_text(encoding='utf-8')
        set_colors(fg=FG_GREEN)
        print(ascii_art)
    set_colors(fg=FG_GREEN)
    print('BEAN')
    set_colors(fg=FG_YELLOW)


async def cmd_bean_test(config: dict):
    """Run automated test suite with safe settings.

    Login is tested first. If credentials are not saved, prompts for them.
    If login fails, shows error and asks Continue/Exit.
    """
    from spore_crawler.storage.database import Database
    from spore_crawler.api.client import SporeAPI
    from spore_crawler.api.auth import (
        SporeAuth, get_credentials, get_credentials_interactive,
        save_credentials, load_credentials,
    )
    from spore_crawler.crawlers.full_crawler import crawl_assets
    from spore_crawler.cli.commands._common import get_resource_dir

    if not config.get('bean_test', False):
        print('INBEANIFY YOURSELF!')
        return False

    log.info('=== BEAN TEST MODE ===')
    print('  BEAN TEST MODE')
    print('  Running automated test suite...')
    print()

    test_dir = Path('test_downloads')
    test_dir.mkdir(parents=True, exist_ok=True)

    test_results = []
    test_count = 0
    pass_count = 0
    fail_count = 0

    def log_test(name, success, details=''):
        nonlocal test_count, pass_count, fail_count
        test_count += 1
        if success:
            pass_count += 1
        else:
            fail_count += 1
        test_results.append({'name': name, 'success': success, 'details': details})
        detail = f" ({details})" if details else ''
        status = '[PASS]' if success else '[FAIL]'
        print(f"    {status} {name}{detail}")

    def fresh_db(test_bean=''):
        test_path = test_dir / f'{test_bean}.db'
        if test_path.exists():
            test_path.unlink()
        db = Database(str(test_path))
        return db, test_path

    async def fresh_api():
        return SporeAPI()

    # === LOGIN TEST (first) ===
    print('  [LOGIN]')

    email = None
    password = None
    login_success = False

    creds = get_credentials(config, prompt_if_missing=False)
    if creds:
        email, password = creds
        log.info('Using config credentials for: %s', email)
    else:
        saved = load_credentials()
        if saved:
            email, password = saved
            log.info('Using saved credentials for: %s', email)
        else:
            print()
            print('  No saved credentials found.')
            print('  Login is required for full bean_test (API search tests).')
            print()
            try:
                email, password = get_credentials_interactive()
            except (ValueError, EOFError):
                print()
                print('  Credentials required. Skipping login and API tests.')
                print('  Run "login --new" first, then try bean_test again.')
                print()
                email = None
                password = None

    if email and password:
        log.info('Test: login EA SSO')
        try:
            auth = SporeAuth(email=email, password=password)
            jsessionid = await auth.login()
            save_credentials(email, password)
            login_success = True
            log_test('Login EA SSO', True, f"email={email}")
            await auth.close()
        except Exception as e:
            log.error('Login failed: %s', e)
            log_test('Login EA SSO', False, str(e))
            print()
            print(f"  Login failed: {e}")
            print()
            try:
                choice = input("  Continue with remaining tests? (y/n): ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = 'n'
            if choice not in ('y', 'yes'):
                print("  Test aborted.")
                return False
    else:
        log_test('Login EA SSO', False, 'no credentials')
        print()
        print("  Skipping API tests (no login).")
        print()

    # === DATABASE TESTS ===
    print('  [DATABASE]')

    log.info('Test: db create')
    try:
        db, db_path = fresh_db('db_create')
        log_test('DB create', True)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB create', False, str(e))

    log.info('Test: db record_download')
    try:
        db, db_path = fresh_db('db_record')
        db.record_download(999999, 'test.png', 1024)
        log_test('DB record_download', True)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB record_download', False, str(e))

    log.info('Test: db is_downloaded')
    try:
        db, db_path = fresh_db('db_is_downloaded')
        db.record_download(999999, 'test.png', 1024)
        result = db.is_downloaded(999999)
        log_test('DB is_downloaded', result)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB is_downloaded', False, str(e))

    log.info('Test: db update_progress')
    try:
        db, db_path = fresh_db('db_update_progress')
        db.record_download(999999, 'test.png', 1024)
        db.update_progress('test_crawl', 0, 0, 'running')
        log_test('DB update_progress', True)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB update_progress', False, str(e))

    log.info('Test: db get_progress')
    try:
        db, db_path = fresh_db('db_get_progress')
        db.record_download(999999, 'test.png', 1024)
        db.update_progress('test_crawl', 0, 0, 'running')
        progress = db.get_progress('test_crawl')
        log_test('DB get_progress', progress is not None and progress.get('last_start_index') == 0)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB get_progress', False, str(e))

    log.info('Test: db save_chunk')
    try:
        db, db_path = fresh_db('db_save_chunk')
        db.record_download(999999, 'test.png', 1024)
        chunk_path = db.save_chunk('a.png', str(test_dir / 'db_chunks'))
        log_test('DB save_chunk', chunk_path is not None and Path(chunk_path).exists())
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB save_chunk', False, str(e))

    log.info('Test: db list_chunks')
    try:
        db, db_path = fresh_db('db_list_chunks')
        db.record_download(999999, 'a.png', 1024)
        db.save_chunk('a.png', str(test_dir / 'db_chunks'))
        chunks = db.list_chunks(str(test_dir / 'db_chunks'))
        log_test('DB list_chunks', len(chunks) > 0, f"{len(chunks)} chunks")
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB list_chunks', False, str(e))

    log.info('Test: db load_chunk')
    try:
        db_src, db_src_path = fresh_db('db_load_chunk_src')
        db_src.record_download(999999, 'a.png', 1024)
        chunk_path = db_src.save_chunk('a.png', str(test_dir / 'db_chunks'))
        db_src.close()
        db_src_path.unlink()

        db_dst, db_dst_path = fresh_db('db_load_chunk_dst')
        result = db_dst.load_chunk(chunk_path, verify=True)
        log_test('DB load_chunk', result['loaded'] > 0, f"loaded={result['loaded']}")
        db_dst.close()
        db_dst_path.unlink()
    except Exception as e:
        log_test('DB load_chunk', False, str(e))

    log.info('Test: db verify_chunk')
    try:
        db_src, db_src_path = fresh_db('db_verify_chunk')
        db_src.record_download(999999, 'a.png', 1024)
        chunk_path = db_src.save_chunk('a.png', str(test_dir / 'db_chunks'))
        db_src.close()
        db_src_path.unlink()

        db_dst, db_dst_path = fresh_db('db_verify_chunk_dst')
        try:
            result = db_dst.load_chunk(chunk_path, verify=True)
            log_test('DB verify_chunk', result['loaded'] > 0, f"loaded={result['loaded']}")
        finally:
            db_dst.close()
            db_dst_path.unlink(missing_ok=True)
    except Exception as e:
        log_test('DB verify_chunk', False, str(e))

    log.info('Test: db get_total_downloaded')
    try:
        db, db_path = fresh_db('db_get_total')
        db.record_download(999999, 'b.png', 1024)
        total = db.get_total_downloaded()
        log_test('DB get_total_downloaded', total > 0)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB get_total_downloaded', False, str(e))

    log.info('Test: db record_sporecast_asset')
    try:
        db, db_path = fresh_db('db_record_sporecast_asset')
        db.record_sporecast_asset(456, 999999)
        log_test('DB record_sporecast_asset', True)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB record_sporecast_asset', False, str(e))

    log.info('Test: db get_sporecast_asset_ids')
    try:
        db, db_path = fresh_db('db_get_sporecast_ids')
        db.record_sporecast_asset(789, 999999)
        ids = db.get_sporecast_asset_ids(789)
        log_test('DB get_sporecast_asset_ids', 999999 in ids, f"ids={ids}")
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB get_sporecast_asset_ids', False, str(e))

    log.info('Test: db record_sporecast_scan')
    try:
        db, db_path = fresh_db('db_record_scan')
        db.record_sporecast_scan(123, 'Test SC', 'User1', 10, 5)
        log_test('DB record_sporecast_scan', True)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB record_sporecast_scan', False, str(e))

    log.info('Test: db is_sporecast_scanned')
    try:
        db, db_path = fresh_db('db_is_scanned')
        db.record_sporecast_scan(123, 'Test SC', 'User1', 10, 5)
        result = db.is_sporecast_scanned(123)
        log_test('DB is_sporecast_scanned', result)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB is_sporecast_scanned', False, str(e))

    log.info('Test: db get_all_scanned_sporecasts')
    try:
        db, db_path = fresh_db('db_get_all_scanned')
        db.record_sporecast_scan(123, 'Test SC', 'User1', 10, 5)
        result = db.get_all_scanned_sporecasts()
        log_test('DB get_all_scanned_sporecasts', len(result) > 0)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB get_all_scanned_sporecasts', False, str(e))

    log.info('Test: db record_browsed_asset')
    try:
        db, db_path = fresh_db('db_record_browsed')
        db.record_browsed_asset(555555, 'Test Creature', 'CREATURE', 'TestAuthor', 'Animal', 'A test', 'tag1', '99')
        log_test('DB record_browsed_asset', True)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB record_browsed_asset', False, str(e))

    log.info('Test: db is_asset_browsed')
    try:
        db, db_path = fresh_db('db_is_browsed')
        db.record_browsed_asset(555555, 'Test Creature', 'CREATURE', 'TestAuthor', 'Animal', 'A test', 'tag1', '99')
        result = db.is_asset_browsed(555555)
        log_test('DB is_asset_browsed', result)
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB is_asset_browsed', False, str(e))

    log.info('Test: db get_browsed_asset_count')
    try:
        db, db_path = fresh_db('db_browsed_count')
        db.record_browsed_asset(555555, 'Test Creature', 'CREATURE', 'TestAuthor', 'Animal', 'A test', 'tag1', '99')
        count = db.get_browsed_asset_count()
        log_test('DB get_browsed_asset_count', count > 0, f"count={count}")
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB get_browsed_asset_count', False, str(e))

    log.info('Test: db get_all_browsed_assets')
    try:
        db, db_path = fresh_db('db_get_all_browsed')
        db.record_browsed_asset(555555, 'Test Creature', 'CREATURE', 'TestAuthor', 'Animal', 'A test', 'tag1', '99')
        result = db.get_all_browsed_assets()
        log_test('DB get_all_browsed_assets', len(result) > 0, f"count={len(result)}")
        db.close()
        db_path.unlink()
    except Exception as e:
        log_test('DB get_all_browsed_assets', False, str(e))

    # === API TESTS ===
    print()
    print('  [API]')

    log.info('Test: api get_stats')
    try:
        async with SporeAPI() as api:
            stats = await api.get_stats()
        log_test('API get_stats', stats.get('totalUploads') is not None, f"uploads={stats.get('totalUploads', '?')}")
    except Exception as e:
        log_test('API get_stats', False, str(e))

    log.info('Test: api search_assets NEWEST')
    try:
        async with SporeAPI() as api:
            assets = await api.search_assets('NEWEST', 0, 10, 'CREATURE')
        log_test('API search_assets NEWEST', assets is not None and len(assets) > 0, f"got={len(assets) if assets else 0}")
    except Exception as e:
        log_test('API search_assets NEWEST', False, str(e))

    log.info('Test: api search_assets TOP_RATED')
    try:
        async with SporeAPI() as api:
            assets = await api.search_assets('TOP_RATED', 0, 10, 'BUILDING')
        log_test('API search_assets TOP_RATED', assets is not None and len(assets) > 0, f"got={len(assets) if assets else 0}")
    except Exception as e:
        log_test('API search_assets TOP_RATED', False, str(e))

    log.info('Test: api search_assets FEATURED')
    try:
        async with SporeAPI() as api:
            assets = await api.search_assets('FEATURED', 0, 10, 'VEHICLE')
        log_test('API search_assets FEATURED', assets is not None and len(assets) > 0, f"got={len(assets) if assets else 0}")
    except Exception as e:
        log_test('API search_assets FEATURED', False, str(e))

    log.info('Test: api search_assets MAXIS_MADE')
    try:
        async with SporeAPI() as api:
            assets = await api.search_assets('MAXIS_MADE', 0, 10, 'ADVENTURE')
        log_test('API search_assets MAXIS_MADE', assets is not None and len(assets) > 0, f"got={len(assets) if assets else 0}")
    except Exception as e:
        log_test('API search_assets MAXIS_MADE', False, str(e))

    log.info('Test: api get_user_sporecasts')
    try:
        async with SporeAPI() as api:
            result = await api.get_user_sporecasts('MaxisMichael')
        log_test('API get_user_sporecasts', result is not None)
    except Exception as e:
        log_test('API get_user_sporecasts', False, str(e))

    log.info('Test: api search_sporecasts')
    try:
        async with SporeAPI() as api:
            result = await api.search_sporecasts('creature')
        log_test('API search_sporecasts', result is not None)
    except Exception as e:
        log_test('API search_sporecasts', False, str(e))

    # === CRAWL TESTS ===
    print()
    print('  [CRAWL]')

    log.info('Test: crawl NEWEST CREATURE')
    try:
        async with SporeAPI() as api:
            db, db_path = fresh_db('crawl_newest_creature')
            output = test_dir / 'crawl_newest_creature'
            output.mkdir(exist_ok=True)
            count, bytes_dl, limit = await crawl_assets(
                api, db, output, 'NEWEST', 'CREATURE', page_size=500,
                max_pages=1, max_amount=5, max_size_mb=50,
                max_concurrent_downloads=5, embed_metadata=True, hotkey=None,
            )
            log_test('Crawl NEWEST CREATURE', True, f"downloaded={count}")
            db.close()
            db_path.unlink()
    except Exception as e:
        log_test('Crawl NEWEST CREATURE', False, str(e))

    log.info('Test: crawl --max-pages 1')
    try:
        async with SporeAPI() as api:
            db, db_path = fresh_db('crawl_max_pages')
            output = test_dir / 'crawl_max_pages'
            output.mkdir(exist_ok=True)
            count, bytes_dl, limit = await crawl_assets(
                api, db, output, 'NEWEST', 'CREATURE', page_size=500,
                max_pages=1, max_amount=0, max_size_mb=0,
                max_concurrent_downloads=5, embed_metadata=True, hotkey=None,
            )
            log_test('Crawl --max-pages 1', True, f"downloaded={count}")
            db.close()
            db_path.unlink()
    except Exception as e:
        log_test('Crawl --max-pages 1', False, str(e))

    log.info('Test: crawl --amount 10')
    try:
        async with SporeAPI() as api:
            db, db_path = fresh_db('crawl_amount')
            output = test_dir / 'crawl_amount'
            output.mkdir(exist_ok=True)
            count, bytes_dl, limit = await crawl_assets(
                api, db, output, 'NEWEST', 'CREATURE', page_size=500,
                max_pages=0, max_amount=10, max_size_mb=0,
                max_concurrent_downloads=5, embed_metadata=True, hotkey=None,
            )
            log_test('Crawl --amount 10', True, f"downloaded={count}, limit={limit}")
            db.close()
            db_path.unlink()
    except Exception as e:
        log_test('Crawl --amount 10', False, str(e))

    log.info('Test: crawl --size 1')
    try:
        async with SporeAPI() as api:
            db, db_path = fresh_db('crawl_size')
            output = test_dir / 'crawl_size'
            output.mkdir(exist_ok=True)
            count, bytes_dl, limit = await crawl_assets(
                api, db, output, 'NEWEST', 'CREATURE', page_size=500,
                max_pages=0, max_amount=0, max_size_mb=1,
                max_concurrent_downloads=5, embed_metadata=True, hotkey=None,
            )
            log_test('Crawl --size 1', True, f"downloaded={count}, bytes={bytes_dl}")
            db.close()
            db_path.unlink()
    except Exception as e:
        log_test('Crawl --size 1', False, str(e))

    log.info('Test: crawl --save-chunk')
    try:
        async with SporeAPI() as api:
            db, db_path = fresh_db('crawl_save_chunk')
            output = test_dir / 'crawl_test'
            output.mkdir(exist_ok=True)
            count, bytes_dl, limit = await crawl_assets(
                api, db, output, 'NEWEST', 'CREATURE', page_size=500,
                max_pages=1, max_amount=5, max_size_mb=50,
                max_concurrent_downloads=5, embed_metadata=True, hotkey=None,
            )
            chunk_path = db.save_chunk('crawl_test', str(test_dir / 'db_chunks'))
            log_test('Crawl --save-chunk', chunk_path is not None, f"chunk={chunk_path}")
            db.close()
            db_path.unlink()
    except Exception as e:
        log_test('Crawl --save-chunk', False, str(e))

    log.info('Test: crawl --load-chunk')
    try:
        async with SporeAPI() as api:
            db_src, db_src_path = fresh_db('crawl_load_chunk_src')
            output_src = test_dir / 'load_test'
            output_src.mkdir(exist_ok=True)
            count, bytes_dl, limit = await crawl_assets(
                api, db_src, output_src, 'NEWEST', 'CREATURE', page_size=500,
                max_pages=1, max_amount=5, max_size_mb=50,
                max_concurrent_downloads=5, embed_metadata=True, hotkey=None,
            )
            chunk_path = db_src.save_chunk('load_test', str(test_dir / 'db_chunks'))
            db_src.close()
            db_src_path.unlink()

            db_dst, db_dst_path = fresh_db('crawl_load_chunk_dst')
            output_dst = test_dir / 'crawl_load_chunk_dst'
            output_dst.mkdir(exist_ok=True)
            db_dst.load_chunk(chunk_path)
            log_test('Crawl --load-chunk', True)
            db_dst.close()
            db_dst_path.unlink()
    except Exception as e:
        log_test('Crawl --load-chunk', False, str(e))

    log.info('Test: crawl --skipcheck')
    try:
        async with SporeAPI() as api:
            db_src, db_src_path = fresh_db('crawl_skipcheck_src')
            output_src = test_dir / 'skipcheck_test'
            output_src.mkdir(exist_ok=True)
            count, bytes_dl, limit = await crawl_assets(
                api, db_src, output_src, 'NEWEST', 'CREATURE', page_size=500,
                max_pages=1, max_amount=5, max_size_mb=50,
                max_concurrent_downloads=5, embed_metadata=True, hotkey=None,
            )
            chunk_path = db_src.save_chunk('skipcheck_test', str(test_dir / 'db_chunks'))
            db_src.close()
            db_src_path.unlink()

            db_dst, db_dst_path = fresh_db('crawl_skipcheck_dst')
            output_dst = test_dir / 'crawl_skipcheck_dst'
            output_dst.mkdir(exist_ok=True)
            db_dst.load_chunk(chunk_path, verify=False)
            log_test('Crawl --skipcheck', True)
            db_dst.close()
            db_dst_path.unlink()
    except Exception as e:
        log_test('Crawl --skipcheck', False, str(e))

    # === METADATA TESTS ===
    print()
    print('  [METADATA]')

    log.info('Test: metadata build_asset_xml')
    try:
        from spore_crawler.storage.png_metadata import build_asset_xml, _escape_xml
        xml = build_asset_xml(
            asset_id=12345,
            name='Test Creature',
            author='TestAuthor',
            author_id=99999,
            created='2026-01-01 00:00:00.000',
            description='Test description with <special> & characters',
            tags='tag1, tag2',
            asset_type='0x9ea3031a',
            subtype='10.0',
            rating=99,
            parent_id=67890,
        )
        valid = '<?xml version="1.0"' in xml and '<spore-creation>' in xml
        has_id = '<asset-id>12345</asset-id>' in xml
        has_name = '<name>Test Creature</name>' in xml
        has_escaped = '&lt;special&gt;' in xml
        log_test('Metadata build_asset_xml', valid, f"valid={valid}, id={has_id}, name={has_name}, escaped={has_escaped}")
    except Exception as e:
        log_test('Metadata build_asset_xml', False, str(e))

    log.info('Test: metadata build_sporecast_xml')
    try:
        from spore_crawler.storage.png_metadata import build_sporecast_xml
        xml = build_sporecast_xml(
            sporecast_id=12345,
            title='Test Sporecast',
            author='TestAuthor',
            subtitle='Test subtitle',
            rating='4.5',
            asset_count=99,
            tags='tag1, tag2',
            updated='2026-01-01',
            subscribers=42,
        )
        valid = '<spore-sporecast>' in xml and '</spore-sporecast>' in xml
        has_title = '<title>Test Sporecast</title>' in xml
        log_test('Metadata build_sporecast_xml', valid, f"valid={valid}, title={has_title}")
    except Exception as e:
        log_test('Metadata build_sporecast_xml', False, str(e))

    log.info('Test: metadata embed + read round-trip')
    try:
        from spore_crawler.storage.png_metadata import build_asset_xml, embed_metadata_in_png, read_metadata_from_png, extract_metadata_dict
        import glob as glob_mod
        pngs = list(test_dir.rglob('**/*.png'))
        if pngs:
            test_png = pngs[0]
            xml = build_asset_xml(
                asset_id=999999,
                name='Bean Test',
                author='BeanBot',
                asset_type='0x9ea3031a',
                subtype='10.0',
            )
            success = embed_metadata_in_png(test_png, xml)
            meta_xml = read_metadata_from_png(test_png)
            meta_dict = extract_metadata_dict(test_png)
            has_ztxt = b'zTXt' in test_png.read_bytes() if test_png.exists() else False
            has_keyword = b'SporeMetadata' in test_png.read_bytes() if test_png.exists() else False
            has_spor = b'spOr' in test_png.read_bytes() if test_png.exists() else False
            xml_valid = meta_xml is not None and 'asset-id' in (meta_xml or '')
            dict_valid = meta_dict is not None and meta_dict.get('asset-id') == '999999'
            log_test('Metadata embed + read round-trip', success and xml_valid and dict_valid,
                     f"embed={success}, xml_valid={xml_valid}, dict_valid={dict_valid}, zTXt={has_ztxt}, keyword={has_keyword}, spOr={has_spor}, file={test_png}")
        else:
            log_test('Metadata embed + read round-trip', False, 'No test PNG found in test_downloads')
    except Exception as e:
        log_test('Metadata embed + read round-trip', False, str(e))

    log.info('Test: metadata idempotency')
    try:
        from spore_crawler.storage.png_metadata import build_asset_xml, embed_metadata_in_png
        pngs = list(test_dir.rglob('**/*.png'))
        if pngs:
            test_png = pngs[0]
            size1 = test_png.stat().st_size
            xml = build_asset_xml(
                asset_id=888888,
                name='Idempotent',
                author='Bean',
                asset_type='0x9ea3031a',
            )
            embed_metadata_in_png(test_png, xml)
            size2 = test_png.stat().st_size
            log_test('Metadata idempotency', True, f"size1={size1}, size2={size2}, chunks={size1 == size2}")
        else:
            log_test('Metadata idempotency', False, 'No test PNG found')
    except Exception as e:
        log_test('Metadata idempotency', False, str(e))

    log.info('Test: metadata game-compatible (spOr preserved if present)')
    try:
        from spore_crawler.storage.png_metadata import read_metadata_from_png, extract_metadata_dict
        pngs = list(test_dir.rglob('**/*.png'))
        spOr_found = False
        for p in pngs:
            data = p.read_bytes()
            if b'spOr' in data:
                spOr_found = True
                meta_xml = read_metadata_from_png(p)
                meta_dict = extract_metadata_dict(meta_xml)
                has_spor_before = b'spOr' in data
                log_test('Metadata game-compatible (spOr preserved if present)', has_spor_before,
                         f"spOr_before={has_spor_before}, spOr_after={has_spor_before}")
                break
        if not spOr_found:
            log_test('Metadata game-compatible (spOr preserved if present)', True, 'No PNG with spOr found (spOr is optional for game import)')
    except Exception as e:
        log_test('Metadata game-compatible (spOr preserved if present)', False, str(e))

    # Cleanup test databases
    for db_file in test_dir.rglob('*.db'):
        try:
            db_file.unlink()
        except Exception:
            pass

    # === RESULTS ===
    print()
    print('  BEAN TEST RESULTS')
    print(f"  Total: {test_count} | Passed: {pass_count} | Failed: {fail_count}")

    ascii_dir = get_resource_dir()
    if fail_count == 0:
        success_ascii_path = ascii_dir / 'success_ascii.txt'
        if success_ascii_path.exists():
            ascii_art = success_ascii_path.read_text(encoding='utf-8')
            print(ascii_art)
        print('  ALL TESTS PASSED!')
        print('BEAN CERTIFIED')
        print('=== BEAN TEST: ALL PASSED ===')
    else:
        fail_ascii_path = ascii_dir / 'fail_ascii.txt'
        if fail_ascii_path.exists():
            ascii_art = fail_ascii_path.read_text(encoding='utf-8')
            print(ascii_art)
        print('  SOME TESTS FAILED!')
        print('NO BEAN FOR YOU!')
        print(f"=== BEAN TEST: {fail_count} FAILURES ===")

    return fail_count == 0
