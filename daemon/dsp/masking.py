"""
ReaBot DSP - Masking Analysis

Analyzes frequency overlap between multiple tracks to detect masking.
"""

from typing import Dict, List, Any

def analyze_masking(tracks_analysis: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Compare multiple tracks to find frequency masking.
    
    Args:
        tracks_analysis: List of dicts, each containing a track's analysis
            and metadata. Expected format:
            [{
                "wav_path": "...",
                "track_metadata": {"name": "Kick"},
                "analysis": {"band_energy": {...}, ...}
            }, ...]
            
    Returns:
        Dict detailing masking conflicts.
    """
    if len(tracks_analysis) < 2:
        return {"conflicts": []}
        
    conflicts = []
    
    # Define bands we care about for masking
    bands_to_check = [
        "sub_20_60", "low_60_200", "low_mid_200_500", 
        "mid_500_2k", "upper_mid_2k_5k"
    ]
    
    # Compare every pair of tracks
    for i in range(len(tracks_analysis)):
        for j in range(i + 1, len(tracks_analysis)):
            track_a = tracks_analysis[i]
            track_b = tracks_analysis[j]
            
            name_a = track_a.get("track_metadata", {}).get("name", f"Track {i+1}")
            name_b = track_b.get("track_metadata", {}).get("name", f"Track {j+1}")
            
            bands_a = track_a.get("analysis", {}).get("band_energy", {})
            bands_b = track_b.get("analysis", {}).get("band_energy", {})
            
            # Find bands where both tracks have significant energy (> 15%)
            overlap_bands = []
            for band in bands_to_check:
                energy_a = bands_a.get(band, 0)
                energy_b = bands_b.get(band, 0)
                
                if energy_a > 0.15 and energy_b > 0.15:
                    # Calculate overlap coefficient (0 to 1)
                    # 1.0 means identical energy in that band
                    overlap = min(energy_a, energy_b) / max(energy_a, energy_b)
                    
                    overlap_bands.append({
                        "band": band,
                        "energy_a": energy_a,
                        "energy_b": energy_b,
                        "overlap_coefficient": round(overlap, 2)
                    })
                    
            if overlap_bands:
                conflicts.append({
                    "track_a": name_a,
                    "track_b": name_b,
                    "overlap_bands": overlap_bands
                })
                
    return {"conflicts": conflicts}
