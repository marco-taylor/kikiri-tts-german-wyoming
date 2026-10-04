"""Exact native forward split at the duration boundary; no new text chunking."""

import io
import soundfile as sf
import server as b
import torch

quiet = b.KPipeline(lang_code="d", repo_id="hexgrad/Kokoro-82M", model=False)


def load(voice):
    r = b.load_voice(voice)
    assert all(
        p.dtype == torch.float32
        for p in r["model"].parameters()
        if p.is_floating_point()
    ), "FP32 reference required"
    if not r.get("materialized"):
        for m in r["model"].modules():
            if hasattr(m, "parametrizations") and "weight" in m.parametrizations:
                torch.nn.utils.parametrize.remove_parametrizations(
                    m, "weight", leave_parametrized=True
                )
        r["materialized"] = True
    return r


def prepare(text, r, segments=None):
    chunks = []
    model = r["model"]
    for result in segments if segments is not None else quiet(text):
        ps = result.phonemes
        ids = list(
            filter(lambda i: i is not None, map(lambda p: model.vocab.get(p), ps))
        )
        assert len(ids) + 2 <= model.context_length
        ids = torch.LongTensor([[0, *ids, 0]]).to(model.device)
        ref_s = r["voice"][len(ps) - 1].to(model.device)
        lengths = torch.full(
            (ids.shape[0],), ids.shape[-1], device=ids.device, dtype=torch.long
        )
        mask = (
            torch.arange(lengths.max())
            .unsqueeze(0)
            .expand(lengths.shape[0], -1)
            .type_as(lengths)
        )
        mask = torch.gt(mask + 1, lengths.unsqueeze(1)).to(model.device)
        bert = model.bert(ids, attention_mask=(~mask).int())
        d_en = model.bert_encoder(bert).transpose(-1, -2)
        s = ref_s[:, 128:]
        d = model.predictor.text_encoder(d_en, s, lengths, mask)
        x, _ = model.predictor.lstm(d)
        duration = model.predictor.duration_proj(x)
        duration_unscaled = torch.sigmoid(duration).sum(axis=-1)
        duration = duration_unscaled / 1.0
        pred_dur = torch.round(duration).clamp(min=1).long().squeeze()
        chunks.append(
            dict(
                duration_unscaled=duration_unscaled,
                ids=ids,
                ref_s=ref_s,
                lengths=lengths,
                mask=mask,
                d=d,
                pred_dur=pred_dur,
                samples=int(pred_dur.sum()) * 600,
                phonemes=ps,
                text=result.graphemes,
            )
        )
    return chunks


def finish(c, r):
    model = r["model"]
    ids = c["ids"]
    pred = c["pred_dur"]
    d = c["d"]
    ref_s = c["ref_s"]
    s = ref_s[:, 128:]
    indices = torch.repeat_interleave(
        torch.arange(ids.shape[1], device=model.device), pred
    )
    aln = torch.zeros((ids.shape[1], indices.shape[0]), device=model.device)
    aln[indices, torch.arange(indices.shape[0])] = 1
    aln = aln.unsqueeze(0)
    en = d.transpose(-1, -2) @ aln
    f0, n = model.predictor.F0Ntrain(en, s)
    t_en = model.text_encoder(ids, c["lengths"], c["mask"])
    asr = t_en @ aln
    audio = (
        model.decoder(asr, f0, n, ref_s[:, :128]).squeeze().cpu().numpy().reshape(-1)
    )
    assert len(audio) == c["samples"]
    return audio


def pcm(audio):
    decoded, rate = sf.read(
        io.BytesIO(b.make_wav(audio)), dtype="int16", always_2d=True
    )
    assert rate == 24000 and decoded.shape[1] == 1
    return decoded.astype("<i2", copy=False).tobytes()


def speed_chunks(chunks, speed):
    # Cached duration logits: no repeat BERT, duration head or text encoder.
    result = []
    for c in chunks:
        copy = dict(c)
        durations = (
            torch.round(c["duration_unscaled"] / speed).clamp(min=1).long().squeeze()
        )
        copy["pred_dur"] = durations
        copy["samples"] = int(durations.sum()) * 600
        result.append(copy)
    return result
