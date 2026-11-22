import mainBuilding from '../../assets/uust-main-building.jpg'

// Original by FlankerFF: https://commons.wikimedia.org/wiki/File:Bashkir_State_University_(Ufa).jpg
export function CampusArt() {
  return (
    <div className="campus-art">
      <svg className="campus-filter" width="0" height="0" aria-hidden="true">
        <filter id="campus-ink" colorInterpolationFilters="sRGB">
          <feColorMatrix
            type="matrix"
            values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -.32 -1.08 -.11 0 1.29"
            result="shadows"
          />
          <feFlood className="campus-ink" />
          <feComposite in2="shadows" operator="in" />
        </filter>
      </svg>
      <img
        alt="Главный корпус УУНиТ на улице Заки Валиди"
        fetchPriority="high"
        src={mainBuilding}
        title="Bashkir State University (Ufa) · FlankerFF · CC BY-SA 3.0 (https://creativecommons.org/licenses/by-sa/3.0/). Кадрирование и тонирование."
      />
    </div>
  )
}
