"""Tratamento local da câmera com referência do Tascam."""
from pathlib import Path

import numpy as np
import soundfile as sf

rate = 48000
nfft, hop = 4096, 1024
window = np.sqrt(np.hanning(nfft))
frequencies = np.fft.rfftfreq(nfft, 1 / rate)

def spectra(samples):
    padded=np.pad(samples,((nfft//2,nfft),(0,0)))
    frames=np.lib.stride_tricks.sliding_window_view(padded,nfft,axis=0)[::hop]
    return np.fft.rfft(frames*window,axis=2)

def render(spec,length):
    frames=np.fft.irfft(spec,n=nfft,axis=2)*window
    signal=np.zeros(((len(spec)-1)*hop+nfft,2))
    coverage=np.zeros(len(signal))
    for i,frame in enumerate(frames):
        at=i*hop
        signal[at:at+nfft]+=frame.T
        coverage[at:at+nfft]+=window**2
    start=nfft//2
    return signal[start:start+length]/coverage[start:start+length,None]

def smooth(x,radius,axis):
    x=np.moveaxis(x,axis,0)
    padding=[(radius,radius)]+[(0,0)]*(x.ndim-1)
    padded=np.pad(x,padding,mode='edge')
    summed=np.cumsum(np.concatenate([padded[:1]*0,padded]),axis=0)
    width=2*radius+1
    return np.moveaxis((summed[width:]-summed[:-width])/width,0,axis)

def median_near(x,radius,axis):
    x=np.moveaxis(x,axis,-1)
    padding=[(0,0)]*(x.ndim-1)+[(radius,radius)]
    neighborhoods=np.lib.stride_tricks.sliding_window_view(np.pad(x,padding,mode='edge'),2*radius+1,axis=-1)
    return np.moveaxis(np.median(neighborhoods,axis=-1),-1,axis)

def loudness(samples):
    # K-weighting response for 48 kHz and BS.1770 block gating.
    size=1<<(len(samples)+rate-1).bit_length()
    z=np.exp(-2j*np.pi*np.arange(size//2+1)/size)
    shelf=(1.53512485958697-2.69169618940638*z+1.19839281085285*z*z)/(1-1.69065929318241*z+0.73248077421585*z*z)
    highpass=(1-2*z+z*z)/(1-1.99004745483398*z+0.99007225036621*z*z)
    y=np.fft.irfft(np.fft.rfft(samples,n=size,axis=0)*(shelf*highpass)[:,None],n=size,axis=0)[:len(samples)]
    energy=np.sum(y*y,axis=1)
    block=int(rate*.4)
    step=int(rate*.1)
    values=np.array([energy[i:i+block].mean() for i in range(0,len(energy)-block+1,step)])
    values=values[values>10**((-70+.691)/10)]
    if not len(values):
        return float('-inf')
    values=values[values>values.mean()*.1]
    return -.691+10*np.log10(values.mean())

def filter_camera(camera, reference):
    camera_rms = np.sqrt(np.mean(camera ** 2))
    reference_rms = np.sqrt(np.mean(reference ** 2))
    if min(camera_rms, reference_rms) < 1e-8:
        return camera.copy()
    tascam = reference * (camera_rms / reference_rms)
    cam=spectra(camera)
    tas=spectra(tascam)
    x=cam.mean(axis=1)
    y=tas.mean(axis=1)
    p=np.abs(x)**2
    q=np.abs(y)**2
    cross=np.conj(x)*y
    # Estimate recurring spatial cues from bins with sustained tonal energy at both recorders.
    level=np.sqrt((np.abs(x)+1e-9)*(np.abs(y)+1e-9))[:,:430]
    sustained=median_near(level,4,0)
    broadband=median_near(level,4,1)
    tonal=sustained**2/(sustained**2+broadband**2+1e-10)
    weight=tonal**3
    width=level.shape[1]
    target=(cross[:,:width]*weight).sum(axis=0)
    target_p=(p[:,:width]*weight).sum(axis=0)
    target_q=(q[:,:width]*weight).sum(axis=0)
    confidence=np.clip(np.abs(target)/np.sqrt(target_p*target_q+1e-15),0,1)
    cam_power=smooth(p[:,:width],2,0)
    tas_power=smooth(q[:,:width],2,0)
    observed=smooth(cross[:,:width],2,0)
    direction=target/np.maximum(np.abs(target),1e-12)
    phase_agreement=np.real(observed*np.conj(direction))/np.sqrt(cam_power*tas_power+1e-15)
    observed_ratio=10*np.log10((tas_power+1e-12)/(cam_power+1e-12))
    target_ratio=10*np.log10((target_q+1e-12)/(target_p+1e-12))
    ratio_agreement=np.exp(-.5*((observed_ratio-target_ratio)/8)**2)
    support=np.clip((phase_agreement+.20)/.95,0,1)*(.45+.55*ratio_agreement)
    spatial_weight=np.clip((confidence-.16)/.57,0,1)
    spatial_cut=8.0*spatial_weight[None,:]*(1-support)
    tonal_cut=3.5*(1-tonal)**1.3
    attenuation=smooth(smooth(spatial_cut+tonal_cut,2,0),1,1)
    band=frequencies[:width]
    band_fade=np.clip((band-75)/100,0,1)*np.clip((5100-band)/1200,0,1)
    attenuation*=band_fade
    gains=np.ones_like(p)
    gains[:,:width]=10**(-np.minimum(attenuation,9)/20)
    gains*=1-(.62/(1+(frequencies/65)**6))[None,:]
    return render(cam*gains[:,None,:],len(camera))

def estimate_residual(camera, reference, count):
    """Estima o atraso residual, em amostras da câmera, após o sincronismo salvo."""
    factor, search = 12, 1800  # 4 kHz, janela de ±450 ms.
    span = min(count, round(2.9 * rate))
    if span < 2 * rate:
        return 0, 0.0
    offsets = np.unique(np.linspace(0, count - span, min(19, max(1, count // (2 * rate)))).astype(int))
    curves = []
    for offset in offsets:
        prepared = []
        for source in (camera, reference):
            source.seek(offset)
            audio = source.read(span, always_2d=True)
            size = len(audio) // factor * factor
            mono = audio[:size].mean(axis=1).reshape(-1, factor).mean(axis=1)
            prepared.append(mono[16:] - 0.5 * mono[12:-4] - 0.5 * mono[:-16])
        first, second = prepared
        size = min(len(first), len(second))
        first, second = first[search:size-search], second[:size]
        if len(first) < 1000:
            continue
        n = 1 << (len(first) + len(second) - 1).bit_length()
        cross = np.fft.irfft(np.conj(np.fft.rfft(first, n)) * np.fft.rfft(second, n), n)[:2*search+1]
        energy = np.r_[0, np.cumsum(second**2)]
        energies = energy[len(first):len(first)+2*search+1] - energy[:2*search+1]
        norm = np.sqrt(np.sum(first**2) * np.maximum(energies, 0))
        if np.max(norm) > 1e-9:
            curves.append(cross / np.maximum(norm, 1e-9))
    if not curves:
        return 0, 0.0
    scores = np.abs(np.mean(curves, axis=0))
    best = int(np.argmax(scores))
    confidence = float(scores[best])
    if confidence < 0.11:
        return 0, confidence
    fraction = 0.0
    if 0 < best < len(scores) - 1:
        left, peak, right = scores[best-1:best+2]
        curvature = left - 2 * peak + right
        if curvature < 0:
            fraction = 0.5 * (left - right) / curvature
    return round((best - search + fraction) * factor), confidence


def read_stereo(source, start, count):
    begin = max(0, start)
    lead = min(count, begin - start)
    source.seek(min(begin, len(source)))
    data = source.read(count - lead, always_2d=True)
    return np.pad(data, ((lead, count - lead - len(data)), (0, 0)))


def process_camera(camera_path: Path, reference_path: Path, output: Path, duration: float,
                   progress=None):
    """Processa em janelas sobrepostas e mantém a duração na linha do tempo da câmera."""
    total = round(duration * rate)
    block, overlap = 32 * rate, 2 * rate
    with sf.SoundFile(camera_path) as camera, sf.SoundFile(reference_path) as reference:
        for source in (camera, reference):
            if source.samplerate != rate or source.channels != 2:
                raise ValueError("O tratamento precisa de áudio estéreo a 48 kHz.")
            if len(source) < total - round(0.15 * rate):
                raise ValueError("Uma das fontes de áudio não cobre o trecho solicitado.")
        residual, confidence = estimate_residual(camera, reference, min(total, len(camera), len(reference)))
        with sf.SoundFile(output, "w", samplerate=rate, channels=2, subtype="PCM_24") as writer:
            start, tail = 0, None
            while start < total:
                size = min(block, total - start)
                raw = read_stereo(camera, start, size)
                guided = read_stereo(reference, start + residual, size)
                left = min(size, max(0, -start - residual))
                right = max(left, min(size, len(reference) - start - residual))
                out = raw.copy()
                if right - left >= rate // 2 and np.max(np.abs(guided[left:right])) > 1e-7:
                    filtered = filter_camera(raw[left:right], guided[left:right])
                    ramp_length = min(rate // 10, len(filtered) // 2)
                    ramp = np.linspace(0, 1, ramp_length)[:, None]
                    if left:
                        filtered[:ramp_length] = raw[left:left+ramp_length] * (1-ramp) + filtered[:ramp_length] * ramp
                    if right < size:
                        filtered[-ramp_length:] = raw[right-ramp_length:right] * ramp + filtered[-ramp_length:] * (1-ramp)
                    out[left:right] = filtered
                if tail is not None:
                    ramp = np.linspace(0, 1, len(tail))[:, None]
                    out[:len(tail)] = tail * (1 - ramp) + out[:len(tail)] * ramp
                end = start + size
                if end == total:
                    writer.write(out)
                    break
                writer.write(out[:-overlap])
                tail = out[-overlap:]
                start = end - overlap
                if progress:
                    progress(start / total)
            if writer.tell() != total:
                raise RuntimeError("O tratamento de áudio ficou incompleto.")
    if progress:
        progress(1.0)
    return residual / rate, confidence


def prepare_comparison(camera_path: Path, treated_path: Path, original_out: Path, treated_out: Path,
                       duration: float):
    size = round(duration * rate)
    with sf.SoundFile(camera_path) as original:
        camera = read_stereo(original, 0, size)
    treated, _ = sf.read(treated_path, always_2d=True)
    signals = (camera, treated)
    levels = [loudness(signal) for signal in signals]
    if not all(np.isfinite(level) for level in levels):
        raise ValueError("O trecho escolhido está silencioso demais para igualar o volume.")
    max_targets = [level - 2 - 20 * np.log10(np.max(np.abs(signal)))
                   for level, signal in zip(levels, signals)]
    target = min(-20, *max_targets)
    for signal, level, output in zip(signals, levels, (original_out, treated_out)):
        sf.write(output, signal * 10**((target-level)/20), rate, subtype="PCM_24")
