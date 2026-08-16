#!/usr/bin/env python3
"""
GC/NQ coupling detector — shows when Gold & Nasdaq move in parallel vs decouple.
Integrates with trade.py for real-time display.
"""

def detect_coupling(gc_signal, nq_signal):
    """
    Detect GC/NQ coupling state.
    
    Returns: {
        'state': 'PARALLEL' | 'DECOUPLED' | 'UNKNOWN',
        'confidence': 0.0-1.0,
        'reason': str,
        'size_multiplier': 1.0 | 0.5
    }
    """
    if not gc_signal or not nq_signal:
        return {
            'state': 'UNKNOWN',
            'confidence': 0.0,
            'reason': 'Missing signal(s)',
            'size_multiplier': 1.0
        }
    
    gc_dir = gc_signal.get('direction', '?')
    nq_dir = nq_signal.get('direction', '?')
    gc_moon = gc_signal.get('moon_applies', '')
    nq_moon = nq_signal.get('moon_applies', '')
    
    # Classify moon sentiment (benefic vs malefic)
    benefic = ('Venus', 'Jupiter')
    malefic = ('Mars', 'Saturn')
    
    gc_sentiment = None
    if gc_moon in benefic:
        gc_sentiment = 'benefic'
    elif gc_moon in malefic:
        gc_sentiment = 'malefic'
    else:
        gc_sentiment = 'neutral'
    
    nq_sentiment = None
    if nq_moon in benefic:
        nq_sentiment = 'benefic'
    elif nq_moon in malefic:
        nq_sentiment = 'malefic'
    else:
        nq_sentiment = 'neutral'
    
    # Check coupling
    same_direction = gc_dir == nq_dir
    same_sentiment = gc_sentiment == nq_sentiment
    
    if same_direction and same_sentiment:
        state = 'PARALLEL'
        confidence = 0.95 if (gc_sentiment != 'neutral' and nq_sentiment != 'neutral') else 0.70
        reason = f"Both {gc_dir} + {gc_sentiment} moon → synchronized regime"
        size_mult = 1.0  # Full size
    
    elif same_direction and gc_sentiment != 'neutral' and nq_sentiment != 'neutral' and gc_sentiment != nq_sentiment:
        state = 'DECOUPLED'
        confidence = 0.85
        reason = f"Both {gc_dir} but {gc_sentiment} vs {nq_sentiment} moon → conflicting regimes"
        size_mult = 0.75  # Reduce slightly
    
    elif not same_direction and (gc_sentiment != 'neutral' or nq_sentiment != 'neutral'):
        state = 'DECOUPLED'
        confidence = 0.90
        reason = f"Opposite direction ({gc_dir} vs {nq_dir}) + {gc_sentiment}/{nq_sentiment} → inflation/deflation hedge"
        size_mult = 0.5  # Half size for hedging
    
    else:
        state = 'UNCERTAIN'
        confidence = 0.40
        reason = "Mixed or weak signals — monitor"
        size_mult = 0.75
    
    return {
        'state': state,
        'confidence': confidence,
        'reason': reason,
        'size_multiplier': size_mult,
        'gc_sentiment': gc_sentiment,
        'nq_sentiment': nq_sentiment,
        'same_direction': same_direction,
        'same_sentiment': same_sentiment,
    }


def format_coupling_display(coupling_info):
    """Format coupling info for display in trade.py."""
    state = coupling_info['state']
    conf = coupling_info['confidence']
    reason = coupling_info['reason']
    size_mult = coupling_info['size_multiplier']
    
    # Emoji indicator
    if state == 'PARALLEL':
        emoji = '🔗'
    elif state == 'DECOUPLED':
        emoji = '⚡'
    else:
        emoji = '❓'
    
    # Size hint
    if size_mult >= 0.95:
        size_hint = "FULL SIZE"
    elif size_mult >= 0.7:
        size_hint = "3/4 SIZE"
    elif size_mult >= 0.5:
        size_hint = "HALF SIZE"
    else:
        size_hint = "1/4 SIZE"
    
    return f"{emoji} {state} ({conf:.0%}) — {reason} [{size_hint}]"


if __name__ == '__main__':
    # Test
    gc_sig = {'direction': 'LONG', 'moon_applies': 'Venus'}
    nq_sig = {'direction': 'LONG', 'moon_applies': 'Venus'}
    
    coupling = detect_coupling(gc_sig, nq_sig)
    print(format_coupling_display(coupling))
