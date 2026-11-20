import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

const statuses = [
  ['aprovado', 'Aprovado'],
  ['reprovado', 'Reprovado'],
  ['em_andamento', 'Em andamento'],
  ['bloqueado', 'Bloqueado'],
  ['nao_executado', 'Não executado'],
];

function readProgress(source) {
  return {
    counts: JSON.parse(source.dataset.counts),
    total: Number(source.dataset.total),
  };
}

function PlayerProgress({ source }) {
  const [{ counts, total }, setProgress] = useState(() => readProgress(source));
  useEffect(() => {
    const update = () => setProgress(readProgress(source));
    source.addEventListener('progresschange', update);
    update();
    return () => source.removeEventListener('progresschange', update);
  }, [source]);

  const done = total - (counts.nao_executado ?? 0);
  const percent = total ? Math.round(done / total * 100) : 0;

  return (
    <section className="player-progress-card" aria-label="Progresso dos casos">
      <div className="player-progress-overview">
        <strong className="player-progress-percent">{percent}%</strong>
        <div className="player-progress-result">
          <div className="player-progress-copy">{done} de {total} casos com resultado</div>
          <div className="player-progress-bar" aria-hidden="true">
            {statuses.slice(0, -1).map(([status, label]) => (
              <span
                key={status}
                data-status={status}
                style={{ width: total ? `${(counts[status] ?? 0) / total * 100}%` : '0%' }}
                title={`${label} · ${counts[status] ?? 0}`}
              />
            ))}
          </div>
        </div>
      </div>
      <ul className="player-progress-legend">
        {statuses.map(([status, label]) => (
          <li key={status} data-status={status}>{label} · {counts[status] ?? 0}</li>
        ))}
      </ul>
    </section>
  );
}

const source = document.getElementById('player-progress');
if (source) createRoot(source).render(<PlayerProgress source={source} />);
