import React from 'react';
import { Globe, Info } from 'lucide-react';

export type LanguageOption = 'auto' | 'en' | 'hi';

export interface LanguageSelectorProps {
  selectedLanguage: LanguageOption;
  onChange: (language: LanguageOption, hint: string | null) => void;
  disabled?: boolean;
}

export const LanguageSelector: React.FC<LanguageSelectorProps> = ({
  selectedLanguage,
  onChange,
  disabled = false,
}) => {
  const handleSelect = (lang: LanguageOption) => {
    if (disabled) return;
    const hint = lang === 'auto' ? null : lang;
    onChange(lang, hint);
  };

  return (
    <div
      role="region"
      aria-label="Language selection"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: '0.4rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
        <span
          id="language-selector-label"
          style={{
            fontSize: '0.8rem',
            fontWeight: 600,
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
          }}
        >
          <Globe size={14} />
          Language:
        </span>

        <div
          role="radiogroup"
          aria-labelledby="language-selector-label"
          style={{
            display: 'inline-flex',
            backgroundColor: 'var(--bg-base)',
            padding: '2px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <button
            type="button"
            role="radio"
            aria-checked={selectedLanguage === 'auto'}
            disabled={disabled}
            onClick={() => handleSelect('auto')}
            style={{
              padding: '0.3rem 0.75rem',
              fontSize: '0.8rem',
              fontWeight: selectedLanguage === 'auto' ? 600 : 400,
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: disabled ? 'not-allowed' : 'pointer',
              backgroundColor:
                selectedLanguage === 'auto' ? 'var(--color-voice)' : 'transparent',
              color: selectedLanguage === 'auto' ? '#FFFFFF' : 'var(--text-secondary)',
              transition: 'background-color 0.15s ease',
            }}
          >
            Auto
          </button>

          <button
            type="button"
            role="radio"
            aria-checked={selectedLanguage === 'en'}
            disabled={disabled}
            onClick={() => handleSelect('en')}
            style={{
              padding: '0.3rem 0.75rem',
              fontSize: '0.8rem',
              fontWeight: selectedLanguage === 'en' ? 600 : 400,
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: disabled ? 'not-allowed' : 'pointer',
              backgroundColor:
                selectedLanguage === 'en' ? 'var(--color-voice)' : 'transparent',
              color: selectedLanguage === 'en' ? '#FFFFFF' : 'var(--text-secondary)',
              transition: 'background-color 0.15s ease',
            }}
          >
            English
          </button>

          <button
            type="button"
            role="radio"
            aria-checked={selectedLanguage === 'hi'}
            disabled={disabled}
            onClick={() => handleSelect('hi')}
            style={{
              padding: '0.3rem 0.75rem',
              fontSize: '0.8rem',
              fontWeight: selectedLanguage === 'hi' ? 600 : 400,
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: disabled ? 'not-allowed' : 'pointer',
              backgroundColor:
                selectedLanguage === 'hi' ? 'var(--color-voice)' : 'transparent',
              color: selectedLanguage === 'hi' ? '#FFFFFF' : 'var(--text-secondary)',
              transition: 'background-color 0.15s ease',
            }}
          >
            Hindi (हिन्दी)
          </button>
        </div>
      </div>

      {/* Auto Explanation note per Requirement 1 */}
      {selectedLanguage === 'auto' && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            fontSize: '0.72rem',
            color: 'var(--text-muted)',
            fontStyle: 'normal',
          }}
        >
          <Info size={12} style={{ flexShrink: 0 }} />
          <span>
            <strong>Auto:</strong> Uses default engine (SenseVoice); no automatic language detection yet. For Hindi, select Hindi explicitly.
          </span>
        </div>
      )}
      {selectedLanguage === 'hi' && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            fontSize: '0.72rem',
            color: 'var(--text-muted)',
          }}
        >
          <Info size={12} style={{ flexShrink: 0 }} />
          <span>
            <strong>Hindi:</strong> Routes directly to IndicConformer-600m acoustic model (`language_hint: &quot;hi&quot;`).
          </span>
        </div>
      )}
    </div>
  );
};

