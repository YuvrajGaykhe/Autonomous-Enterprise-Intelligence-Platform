/**
 * Sound (spec §9.12, D-F-19): off by default. When on, soft keyboard clicks while an agent works
 * and a stamp's thump on a decision, synthesised with Web Audio: there are no audio files.
 */

let context: AudioContext | null = null;

function audio(): AudioContext | null {
  if (context !== null) return context;
  const Context = (globalThis as { AudioContext?: typeof AudioContext }).AudioContext;
  if (Context === undefined) return null;
  try {
    context = new Context();
  } catch {
    return null;
  }
  return context;
}

/** A short burst of filtered noise. */
function noise(seconds: number, frequency: number, gain: number): void {
  const sound = audio();
  if (sound === null) return;
  if (sound.state === 'suspended') void sound.resume();
  const length = Math.max(1, Math.floor(sound.sampleRate * seconds));
  const buffer = sound.createBuffer(1, length, sound.sampleRate);
  const samples = buffer.getChannelData(0);
  for (let index = 0; index < length; index += 1)
    samples[index] = (Math.random() * 2 - 1) * (1 - index / length) ** 3;
  const source = sound.createBufferSource();
  source.buffer = buffer;
  const filter = sound.createBiquadFilter();
  filter.type = 'bandpass';
  filter.frequency.value = frequency;
  const level = sound.createGain();
  level.gain.value = gain;
  source.connect(filter).connect(level).connect(sound.destination);
  source.start();
}

/** One soft key press. */
export function keyClick(): void {
  noise(0.03, 2400 + Math.random() * 1200, 0.08);
}

/** A rubber stamp coming down on paper. */
export function stampThump(): void {
  noise(0.12, 180, 0.5);
  noise(0.05, 1200, 0.12);
}
