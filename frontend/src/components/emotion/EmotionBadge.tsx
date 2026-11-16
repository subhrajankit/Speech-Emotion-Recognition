import React from 'react';
import { Smile, Frown, Flame, AlertCircle, Meh, Sparkles, HelpCircle } from 'lucide-react';
import { Badge } from '../ui/Badge';
import { formatEmotion, formatConfidence } from '../../lib/formatters';

export interface EmotionBadgeProps {
  emotion: unknown;
  confidence: unknown;
  className?: string;
}

export const EmotionBadge: React.FC<EmotionBadgeProps> = ({
  emotion,
  confidence,
  className = '',
}) => {
  const formattedEmotion = formatEmotion(emotion);
  const formattedConf = formatConfidence(confidence);

  if (formattedEmotion === '-') {
    return (
      <Badge variant="neutral" className={className} aria-label="Emotion: -">
        <HelpCircle size={13} style={{ marginRight: '4px' }} />
        <span>Emotion: -</span>
      </Badge>
    );
  }

  const normalized = formattedEmotion.toLowerCase();

  const getEmotionDetails = () => {
    switch (normalized) {
      case 'unknown':
        // Model ran SER and explicitly reported EMO_UNKNOWN/UNK — distinct
        // from missing emotion metadata which renders "Emotion: -" above.
        return {
          icon: <HelpCircle size={13} style={{ marginRight: '4px' }} />,
          variant: 'neutral' as const,
        };
      case 'happy':
        return {
          icon: <Smile size={13} style={{ marginRight: '4px' }} />,
          variant: 'success' as const,
        };
      case 'sad':
        return {
          icon: <Frown size={13} style={{ marginRight: '4px' }} />,
          variant: 'default' as const,
        };
      case 'angry':
        return {
          icon: <Flame size={13} style={{ marginRight: '4px' }} />,
          variant: 'danger' as const,
        };
      case 'fearful':
        return {
          icon: <AlertCircle size={13} style={{ marginRight: '4px' }} />,
          variant: 'warning' as const,
        };
      case 'surprised':
        return {
          icon: <Sparkles size={13} style={{ marginRight: '4px' }} />,
          variant: 'accent' as const,
        };
      case 'neutral':
      default:
        return {
          icon: <Meh size={13} style={{ marginRight: '4px' }} />,
          variant: 'neutral' as const,
        };
    }
  };

  const { icon, variant } = getEmotionDetails();

  return (
    <Badge
      variant={variant}
      className={className}
      aria-label={`Emotion: ${formattedEmotion}, confidence: ${formattedConf}`}
    >
      {icon}
      <span>{formattedEmotion}</span>
      <span style={{ marginLeft: '4px', opacity: 0.75, fontWeight: 400, fontSize: '0.72rem' }}>
        ({formattedConf})
      </span>
    </Badge>
  );
};
