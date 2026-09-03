export function FoundationMesh() {
  const faces = ["front", "back", "right", "left", "top", "bottom"] as const;

  return (
    <div className="foundation-mesh" aria-hidden="true">
      <div className="foundation-scene foundation-scene-left">
        <div className="crypto-cube">
          {faces.map((face) => (
            <span key={`left-${face}`} className={`cube-face cube-face-${face}`} />
          ))}
        </div>
      </div>

      <div className="foundation-scene foundation-scene-right">
        <div className="crypto-cube crypto-cube-right">
          {faces.map((face) => (
            <span key={`right-${face}`} className={`cube-face cube-face-${face}`} />
          ))}
        </div>
      </div>
    </div>
  );
}
