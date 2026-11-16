import React from 'react';
import { Globe, Info } from 'lucide-react';

export type LanguageOption = 'auto' | 'en' | 'hi';

export interface LanguageSelectorProps {
  selectedLanguage: LanguageOption;
  onChange: (language: LanguageOption, hint: string | null) => void;
  disabled?: boolean;
  englishOnly?: boolean;
}

interface LangOptionDef {
  value: LanguageOption;
  label: string;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  selectedLanguage,
  onChange,
  disabled = false,
  englishOnly = false,
}) => {
  const handleSelect = (lang: LanguageOption) => {
    if (disabled || (englishOnly && lang === 'hi')) return;
    const hint = lang === 'auto' ? null : lang;
    onChange(lang, hint);
  };

  const options: LangOptionDef[] = [
    { value: 'auto', label: 'Auto' },
    { value: 'en', label: 'English' },
    ...(!englishOnly ? [{ value: 'hi' as LanguageOption, label: 'Hindi (हिन्दी)' }] : []),
  ];

  return (
    <div
      role="region"
      aria-label="Language selection"
      className="lang-selector"
    >
      <div className="lang-row">
        <span
          id="language-selector-label"
          className="lang-label"
        >
          <Globe size={14} aria-hidden="true" />
          Language:
        </span>

        <div
          role="group"
          aria-labelledby="language-selector-label"
          className="seg-control"
        >
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              aria-pressed={selectedLanguage === opt.value}
              disabled={disabled}
              onClick={() => handleSelect(opt.value)}
              className={`seg-btn ${selectedLanguage === opt.value ? 'active' : ''}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Auto Explanation note per Requirement 1 */}
      {selectedLanguage === 'auto' && (
        <div className="lang-note">
          <Info size={12} style={{ flexShrink: 0 }} aria-hidden="true" />
          <span>
            <strong>Auto:</strong> {englishOnly
              ? 'Uses SenseVoice English ASR; automatic language detection is disabled.'
              : 'Uses default engine (SenseVoice); no automatic language detection yet. For Hindi, select Hindi explicitly.'}
          </span>
        </div>
      )}
      {!englishOnly && selectedLanguage === 'hi' && (
        <div className="lang-note">
          <Info size={12} style={{ flexShrink: 0 }} aria-hidden="true" />
          <span>
            <strong>Hindi:</strong> Routes directly to IndicConformer-600m acoustic model (`language_hint: &quot;hi&quot;`).
          </span>
        </div>
      )}
    </div>
  );
};
