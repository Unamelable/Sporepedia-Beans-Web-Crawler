"""
png_metadata.py - Embeds Spore REST API XML metadata into PNG files as zTXt chunks.

Depends on: None (leaf module, no internal imports)
Used by: crawlers/full_crawler, cli/commands/bean
"""
import struct
import zlib
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def build_asset_xml(
    asset_id: int,
    name: str,
    author: str,
    author_id: Optional[int] = None,
    created: str = "",
    description: str = "",
    tags: str = "",
    asset_type: str = "",
    subtype: str = "",
    rating: str = "",
    parent_id: Optional[int] = None,
    comments: Optional[list] = None,
    sporecast_id: Optional[int] = None,
    sporecast_title: Optional[str] = None,
) -> str:
    """Build XML metadata string for a Spore asset."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<spore-creation>',
        f'  <asset-id>{asset_id}</asset-id>',
        f'  <name>{_escape_xml(name)}</name>',
        f'  <author>{_escape_xml(author)}</author>',
    ]
    if author_id:
        parts.append(f'  <author-id>{author_id}</author-id>')
    if created:
        parts.append(f'  <created>{_escape_xml(created)}</created>')
    if description and description != "NULL":
        parts.append(f'  <description>{_escape_xml(description)}</description>')
    if tags and tags != "NULL":
        parts.append(f'  <tags>{_escape_xml(tags)}</tags>')
    if asset_type:
        parts.append(f'  <type>{asset_type}</type>')
    if subtype:
        parts.append(f'  <subtype>{subtype}</subtype>')
    if rating:
        parts.append(f'  <rating>{rating}</rating>')
    if parent_id:
        parts.append(f'  <parent-id>{parent_id}</parent-id>')
    if sporecast_id:
        parts.append(f'  <sporecast-id>{sporecast_id}</sporecast-id>')
    if sporecast_title:
        parts.append(f'  <sporecast-title>{_escape_xml(sporecast_title)}</sporecast-title>')
    if comments:
        parts.append('  <comments>')
        for c in comments:
            if isinstance(c, dict):
                msg = c.get("message", "")
                sender = c.get("sender", "")
                parts.append(f'    <comment author="{_escape_xml(sender)}">{_escape_xml(msg)}</comment>')
        parts.append('  </comments>')
    parts.append('</spore-creation>')
    return "\n".join(parts)


def build_sporecast_xml(
    sporecast_id: int,
    title: str,
    author: str,
    subtitle: str = "",
    rating: str = "",
    asset_count: int = 0,
    tags: str = "",
    updated: str = "",
    subscribers: int = 0,
) -> str:
    """Build XML metadata string for a Sporecast."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<spore-sporecast>',
        f'  <sporecast-id>{sporecast_id}</sporecast-id>',
        f'  <title>{_escape_xml(title)}</title>',
        f'  <author>{_escape_xml(author)}</author>',
    ]
    if subtitle:
        parts.append(f'  <subtitle>{_escape_xml(subtitle)}</subtitle>')
    if rating:
        parts.append(f'  <rating>{rating}</rating>')
    if asset_count:
        parts.append(f'  <asset-count>{asset_count}</asset-count>')
    if tags and tags != "NULL":
        parts.append(f'  <tags>{_escape_xml(tags)}</tags>')
    if updated:
        parts.append(f'  <updated>{_escape_xml(updated)}</updated>')
    if subscribers:
        parts.append(f'  <subscribers>{subscribers}</subscribers>')
    parts.append('</spore-sporecast>')
    return "\n".join(parts)


def _escape_xml(text) -> str:
    """Escape XML special characters."""
    if not text:
        return ""
    text = str(text)
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;"))


def embed_metadata_in_png(png_path: Path, xml_metadata: str, keyword: str = "SporeMetadata") -> bool:
    """
    Embed XML metadata into a PNG file as a zTXt chunk.
    
    The zTXt chunk uses zlib compression, so the XML is stored efficiently.
    The chunk is placed after IEND (and after spOr if present), which is
    valid PNG spec -- chunks after IEND are ignored by standard viewers
    but can be read by custom tools.
    
    If metadata already exists (same keyword), it is replaced.
    Returns True if successful, False otherwise.
    """
    try:
        data = bytearray(png_path.read_bytes())
        original_size = len(data)
        
        # Verify PNG signature
        if data[:8] != b'\x89PNG\r\n\x1a\n':
            log.warning("Not a valid PNG file: %s", png_path)
            return False
        
        # Check for existing chunks
        has_spor = b'spOr' in data
        existing_pos = _find_chunk(data, keyword)
        
        # Find and remove existing metadata chunk if present
        if existing_pos is not None:
            pos, chunk_total = existing_pos
            del data[pos:pos + chunk_total]
            log.debug("Removed existing '%s' chunk from %s (%d bytes)", keyword, png_path.name, chunk_total)
        
        # Find IEND chunk (end of standard PNG)
        iend_pos = data.find(b'IEND')
        if iend_pos < 0:
            log.warning("No IEND chunk found in %s", png_path)
            return False
        
        # IEND chunk: 4 bytes length (0) + 4 bytes type + 4 bytes CRC = 12 bytes total
        insert_pos = iend_pos + 8  # After IEND chunk (type + CRC, length was 0)
        
        # Build zTXt chunk
        chunk = _build_ztxt_chunk(keyword, xml_metadata)
        
        # Insert the chunk
        data[insert_pos:insert_pos] = chunk
        
        # Write back
        png_path.write_bytes(bytes(data))
        
        new_size = len(data)
        compression_ratio = (1 - len(chunk) / len(xml_metadata.encode('utf-8'))) * 100
        
        log.info("Embedded metadata in %s: %d -> %d bytes (+%d, %.1f%% compression), spOr=%s", 
                 png_path.name, original_size, new_size, new_size - original_size, 
                 compression_ratio, has_spor)
        log.debug("Metadata keyword='%s', xml_size=%d, chunk_size=%d", 
                  keyword, len(xml_metadata.encode('utf-8')), len(chunk))
        return True
        
    except Exception as e:
        log.error("Failed to embed metadata in %s: %s", png_path, e)
        return False


def _find_chunk(data: bytearray, keyword: str) -> tuple[int, int] | None:
    """
    Find a zTXt chunk with the given keyword in PNG data.
    Returns (offset, total_chunk_size) or None.
    """
    keyword_bytes = keyword.encode('latin-1')
    pos = 8  # Skip PNG signature
    
    while pos < len(data) - 8:
        chunk_len = struct.unpack('>I', data[pos:pos+4])[0]
        chunk_type = data[pos+4:pos+8]
        
        if chunk_type == b'zTXt':
            chunk_data = data[pos+8:pos+8+chunk_len]
            null_pos = chunk_data.find(b'\x00')
            if null_pos >= 0:
                chunk_keyword = chunk_data[:null_pos].decode('latin-1')
                if chunk_keyword == keyword:
                    total_size = 12 + chunk_len  # 4 length + 4 type + N data + 4 CRC
                    return (pos, total_size)
        
        pos += 12 + chunk_len
        if chunk_len > 1000000:
            break
    
    return None


def _build_ztxt_chunk(keyword: str, text: str) -> bytes:
    """Build a zTXt PNG chunk."""
    # zTXt format: keyword\0compression_method(1 byte)\ compressed_text
    text_bytes = text.encode('utf-8')
    keyword_bytes = keyword.encode('latin-1')
    
    # Compress the text with zlib
    compressed = zlib.compress(text_bytes)
    
    # Chunk data: keyword + null + compression method (0) + compressed text
    chunk_data = keyword_bytes + b'\x00\x00' + compressed
    
    # Chunk type
    chunk_type = b'zTXt'
    
    # Length (4 bytes big-endian)
    length = struct.pack('>I', len(chunk_data))
    
    # CRC32 over type + data
    crc = struct.pack('>I', zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF)
    
    log.debug("Built zTXt chunk: keyword='%s', text=%d bytes -> compressed=%d bytes (%.1f%% ratio)",
              keyword, len(text_bytes), len(compressed), 
              (1 - len(compressed) / len(text_bytes)) * 100 if text_bytes else 0)
    
    return length + chunk_type + chunk_data + crc


def read_metadata_from_png(png_path: Path) -> Optional[str]:
    """
    Read embedded XML metadata from a PNG file.
    
    Looks for zTXt chunk with keyword "SporeMetadata".
    Returns the XML string if found, None otherwise.
    """
    try:
        data = png_path.read_bytes()
        
        # Find zTXt chunks
        pos = 8  # Skip PNG signature
        chunks_found = 0
        while pos < len(data) - 8:
            # Read chunk
            length = struct.unpack('>I', data[pos:pos+4])[0]
            chunk_type = data[pos+4:pos+8]
            
            if chunk_type == b'zTXt':
                chunks_found += 1
                chunk_data = data[pos+8:pos+8+length]
                # Parse zTXt: keyword\0compression_method\compressed_text
                null_pos = chunk_data.find(b'\x00')
                if null_pos >= 0:
                    keyword = chunk_data[:null_pos].decode('latin-1')
                    if keyword == "SporeMetadata":
                        compression_method = chunk_data[null_pos+1]
                        compressed_data = chunk_data[null_pos+2:]
                        if compression_method == 0:
                            text = zlib.decompress(compressed_data).decode('utf-8')
                            log.debug("Read metadata from %s: keyword='%s', uncompressed=%d bytes", 
                                     png_path.name, keyword, len(text))
                            return text
            
            pos += 12 + length  # 4 length + 4 type + N data + 4 CRC
            
            if length > 1000000:  # Sanity check
                break
        
        if chunks_found > 0:
            log.debug("Found %d zTXt chunks in %s, but none with keyword 'SporeMetadata'", 
                     chunks_found, png_path.name)
                
    except Exception as e:
        log.error("Failed to read metadata from %s: %s", png_path, e)
    return None


def extract_metadata_dict(png_path: Path) -> Optional[dict]:
    """
    Read embedded XML metadata and parse it into a dictionary.
    """
    import xml.etree.ElementTree as ET
    
    xml_text = read_metadata_from_png(png_path)
    if not xml_text:
        return None
    
    try:
        root = ET.fromstring(xml_text)
        result = {}
        for child in root:
            if child.tag == 'comments':
                result['comments'] = [
                    {'author': c.get('author', ''), 'message': c.text or ''}
                    for c in child.findall('comment')
                ]
            else:
                result[child.tag] = child.text or ''
        return result
    except ET.ParseError as e:
        log.error("Failed to parse XML from %s: %s", png_path, e)
        return None


def embed_metadata_from_api_response(png_path: Path, api_xml: str) -> bool:
    """
    Embed raw REST API XML response directly into PNG.
    
    This is the simplest approach -- just embed the XML from /rest/asset/{id}.
    """
    return embed_metadata_in_png(png_path, api_xml, keyword="SporeAPI")


def save_sporecast_metadata(folder: Path, xml_metadata: str) -> bool:
    """
    Save sporecast metadata as XML file in the sporecast folder.
    
    Creates _sporecast_info.xml alongside the downloaded PNGs.
    """
    try:
        xml_path = folder / "_sporecast_info.xml"
        xml_path.write_text(xml_metadata, encoding='utf-8')
        log.info("Saved sporecast metadata to %s", xml_path)
        return True
    except Exception as e:
        log.error("Failed to save sporecast metadata to %s: %s", folder, e)
        return False


def read_sporecast_metadata(folder: Path) -> Optional[dict]:
    """
    Read sporecast metadata from _sporecast_info.xml.
    """
    import xml.etree.ElementTree as ET
    
    xml_path = folder / "_sporecast_info.xml"
    if not xml_path.exists():
        return None
    
    try:
        xml_text = xml_path.read_text(encoding='utf-8')
        root = ET.fromstring(xml_text)
        return {child.tag: child.text or '' for child in root}
    except Exception as e:
        log.error("Failed to read sporecast metadata from %s: %s", xml_path, e)
        return None
