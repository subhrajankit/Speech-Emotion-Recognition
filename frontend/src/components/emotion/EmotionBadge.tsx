import React from 'react';
import { Smile, Frown, Flame, AlertCircle, Meh, Sparkles, HelpCircle } from 'lucide-react';
import { Badge } from '../ui/Badge';

export interface EmotionBadgeProps {
  emotion: string | null;
  confidence: number | null;
  className?: string;
}

export const EmotionBadge: React.FC<EmotionBadgeProps> = ({
  emotion,
  confidence,
  className = '',
}) => {
  if (!emotion) {
    return (
      <Badge variant="neutral" className={className} aria-label="Emotion not available">
        <HelpCircle size={13} style={{ marginRight: '4px' }} />
        <span>Emotion: —</span>
      </Badge>
    );
  }

  const normalized = emotion.toLowerCase();

  const getEmotionDetails = () => {
    switch (normalized) {
      case 'happy':
        return {
          icon: <Smile size={13} style={{ marginRight: '4px' }} />,
          variant: 'success' as const,
          label: 'Happy',
        };
      case 'sad':
        return {
          icon: <Frown size={13} style={{ marginRight: '4px' }} />,
          variant: 'default' as const,
          label: 'Sad',
        };
      case 'angry':
        return {
          icon: <Flame size={13} style={{ marginRight: '4px' }} />,
          variant: 'danger' as const,
          label: 'Angry',
        };
      case 'fearful':
        return {
          icon: <AlertCircle size={13} style={{ marginRight: '4px' }} />,
          variant: 'warning' as const,
          label: 'Fearful',
        };
      case 'surprised':
        return {
          icon: <Sparkles size={13} style={{ marginRight: '4px' }} />,
          variant: 'accent' as const,
          label: 'Surprised',
        };
      case 'neutral':
      default:
        return {
          icon: <Meh size={13} style={{ marginRight: '4px' }} />,
          variant: 'neutral' as const,
          label: normalized.charAt(0).toUpperCase() + normalized.slice(1),
        };
    }
  };

  const { icon, variant, label } = getEmotionDetails();
  const confidenceText =
    typeof confidence === 'number' && !Number.isNaN(confidence)
      ? `${Math.round(confidence * 100)}%`
      : 'not available';

  return (
    <Badge variant={variant} className={className} style={{ textTransform: 'capitalize' }}>
      {icon}
      <span>{label}</span>
      <span style={{ marginLeft: '4px', opacity: 0.7, fontWeight: 400, fontSize: '0.7rem' }}>
        ({confidenceText})
      </span>
    </Badge>
  );
};
